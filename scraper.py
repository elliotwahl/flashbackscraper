# -*- coding: utf-8 -*-
import requests
from bs4 import BeautifulSoup
import time
import csv
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

# --- Konfiguration ---
# Lämna tomt för att bli tillfrågad vid körning
TARGET_URL = ""
OUTPUT_FILE = "flashback_tråd.csv"

# Headers för att efterlikna en riktig webbläsare (viktigt för att undvika blockering)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.flashback.org/',
    'Connection': 'keep-alive'
}

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def derive_output_filename(url):
    parsed = urlparse(url)
    candidate = ""
    match = re.search(r'(t\d+)', url)
    if match:
        candidate = match.group(1)
    else:
        parts = [p for p in parsed.path.split('/') if p]
        if parts:
            candidate = parts[-1]
    if not candidate:
        candidate = "flashback_trad"
    candidate = re.sub(r'[^A-Za-z0-9_-]+', '_', candidate)
    if not candidate:
        candidate = "flashback_trad"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{candidate}_{timestamp}.csv"

def resolve_output_file(start_url):
    # Om OUTPUT_FILE satts manuellt (t.ex. via app.py/tempdir), använd det.
    if OUTPUT_FILE and OUTPUT_FILE != "flashback_tråd.csv":
        return OUTPUT_FILE
    return derive_output_filename(start_url)

def scrape_thread(start_url):
    print(f"🚀 Startar skrapning av: {start_url}")
    
    current_url = start_url
    posts_collected = 0
    page_number = 1
    output_file = resolve_output_file(start_url)
    
    # Öppna filen för skrivning
    with open(output_file, 'w', newline='', encoding='utf-8-sig') as f: # utf-8-sig för att Excel ska läsa åäö rätt
        writer = csv.writer(f, delimiter=';') # Semikolon är ofta bättre för Excel i Sverige
        writer.writerow([
            'Användare',
            'Reg_datum',
            'Antal_inlägg',
            'Datum_Tid',
            'Inlägg_ID',
            'Länk',
            'Avatar_URL',
            'Post_Message'
        ])
        
        while current_url:
            print(f"⏳ Bearbetar sida {page_number}...")
            
            try:
                response = requests.get(current_url, headers=HEADERS, timeout=10)
                response.raise_for_status()
                
                # Flashback använder ofta iso-8859-1, men requests+bs4 brukar lösa det.
                # Vi tvingar encoding om det behövs, men 'response.content' till BS4 är säkrast.
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Kontrollera om vi blivit blockade
                text_content = soup.get_text()
                if "Cloudflare" in text_content or "Access denied" in text_content:
                    print("❌ Blev blockerad av Cloudflare/DDoS-skydd. Försök igen senare eller uppdatera headers.")
                    break

                # Hitta alla inläggsposter (stödjer både gammal och ny layout)
                posts = []
                selectors = [
                    'div.post[id^="post"]',
                    'div[id^="post"][class*="post"]',
                    'div.post_box',
                    'div[id^="post_box_root_"]',
                    'article[data-post-id], article[data-postid]',
                    'div[data-post-id], div[data-postid]',
                    'li[id^="post"]'
                ]
                for sel in selectors:
                    posts = soup.select(sel)
                    if posts:
                        # Filtrera bort rena meddelande-divar
                        posts = [
                            p for p in posts
                            if not re.match(r'^post_message_', p.get('id', '')) and 'post_message' not in (p.get('class') or [])
                        ]
                        if posts:
                            break

                # Fallback: utgå från meddelande-divarna och gå uppåt i trädet
                if not posts:
                    message_divs = soup.select('div.post_message, div[id^="post_message_"], .post__content')
                    for msg in message_divs:
                        parent = msg.find_parent(lambda tag: (
                            tag.name in ['article', 'div', 'li']
                            and (
                                re.match(r'^post\d+', tag.get('id', '')) or
                                'post' in (tag.get('class') or [])
                            )
                        ))
                        if parent and parent not in posts:
                            posts.append(parent)

                if not posts:
                    print(f"⚠️  Inga inlägg hittades på {current_url}.")
                    print("   Sidan kan kräva inloggning eller så har strukturen ändrats.")
                
                for post in posts:
                    try:
                        # 1. ID
                        post_id = post.get('data-post-id') or post.get('data-postid') or post.get('id', '')
                        post_id = re.sub(r'^(post_box_root_|post_message_|postcount|post|p)[-_]?', '', post_id)
                        if not post_id:
                            anchor = post.find('a', id=re.compile(r'(post_anchor_|post_)'))
                            if anchor:
                                anchor_id = anchor.get('id', '') + anchor.get('href', '')
                                m = re.search(r'(\d+)', anchor_id)
                                post_id = m.group(1) if m else ""
                        if not post_id:
                            message_node = post.find(class_=re.compile(r'post_message')) or post.find(id=re.compile(r'post_message_'))
                            if message_node:
                                m = re.search(r'(\d+)', message_node.get('id', ''))
                                post_id = m.group(1) if m else ""
                        if not post_id:
                            post_id = "N/A"

                        # 2. Användare
                        # Kan vara en länk eller bara text om användaren är borttagen
                        user_block = post.select_one('.post-user-info, .post-user, .post__user, .userinfo, .user-info, .post-user-container')
                        user_tag = post.select_one('.post-user-username, a.username, span.username, .post__user a, a[href*="member.php"]')
                        
                        username = user_tag.get_text(strip=True) if user_tag else "Gäst/Borttagen"
                        user_text = user_block.get_text(" ", strip=True) if user_block else ""

                        # Registreringsdatum
                        reg_date = ""
                        if user_text:
                            m = re.search(r'Reg[:\.]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{2}|[0-9]{4}|[0-9]{1,2}\s+\w+\s+[0-9]{4}|[A-Za-zÅÄÖåäö]{3,}\s+[0-9]{4})', user_text)
                            if m:
                                reg_date = m.group(1)

                        # Antal inlägg
                        post_count = ""
                        count_sources = [user_text, post.get_text(" ", strip=True)]
                        for source in count_sources:
                            if not source:
                                continue
                            m = re.search(r'Inl[\u00e4a]gg[:\.]?\s*([0-9][0-9\s\u00a0\.,]*)', source, re.IGNORECASE)
                            if m:
                                # Ta bort mellanslag/nbsp och punkter som tusentalsavskiljare
                                post_count = re.sub(r'[\s\u00a0\.]', '', m.group(1))
                                break
                        
                        # 3. Datum och Tid
                        # Ligger i post-heading. Lite klurigt att extrahera exakt, men vi tar hela texten
                        # och rensar bort användarnamnet för att få kvar datumet.
                        heading = post.select_one('.post-heading, .post-heading-main, .post__details, .posthead, .post-header, time')
                        timestamp = "Okänt datum"
                        if heading:
                            full_text = heading.get_text(" ", strip=True)
                            # Ta bort användarnamnet från början om det finns
                            if full_text.startswith(username):
                                full_text = full_text[len(username):].strip()
                            
                            timestamp = full_text.replace('•', '').strip()
                            # Ibland slutar det med inläggsnummer t.ex "#12", vi kan ta bort det om vi vill, men behåller för kontext.

                        # 4. Innehåll
                        # Postens text (endast själva meddelandet)
                        message_div = (
                            post.find('div', id=re.compile(r'^post_message_')) or
                            post.find('div', class_=re.compile(r'\bpost_message\b')) or
                            post.select_one('.post_message, div[id^="post_message_"], .post__content, .post-body, .post-content')
                        )
                        content = ""
                        if message_div:
                            # Bevara radbrytningar
                            content = message_div.get_text('\n', strip=True)

                        # Avatar-länk
                        avatar_url = ""
                        avatar = post.select_one('img.avatar, .post-user-avatar img, img[alt*="Avatar"], img[src*="avatar"], img[class*="avatar"], img[data-avatar]')
                        if not avatar and user_block:
                            avatar = user_block.select_one('img')
                        if avatar:
                            avatar_url = avatar.get('src', '').strip()
                            if avatar_url.startswith('//'):
                                avatar_url = f"https:{avatar_url}"
                            elif avatar_url.startswith('/'):
                                avatar_url = f"https://www.flashback.org{avatar_url}"
                        
                        # 5. Länk
                        permalink = f"https://www.flashback.org/sp{post_id}" if post_id != "N/A" else current_url

                        writer.writerow([
                            username,
                            reg_date,
                            post_count,
                            timestamp,
                            post_id,
                            permalink,
                            avatar_url,
                            content
                        ])
                        posts_collected += 1
                        
                    except Exception as e:
                        print(f"⚠️  Fel vid tolkning av ett inlägg: {e}")
                        continue

                # Hitta nästa sida
                next_link = (
                    soup.find('link', rel='next') or
                    soup.find('a', rel='next') or
                    soup.find('a', string=re.compile(r'Nästa', re.IGNORECASE)) or
                    soup.select_one('a[aria-label*="Nästa"], a[title*="Nästa"]')
                )
                if next_link and next_link.has_attr('href'):
                    next_url = next_link['href']
                    if not next_url.startswith('http'):
                        current_url = f"https://www.flashback.org{next_url}"
                    else:
                        current_url = next_url
                    
                    page_number += 1
                    # Artig paus för att inte belasta servern
                    time.sleep(1.5)
                else:
                    print("🏁 Inga fler sidor hittades.")
                    current_url = None
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Nätverksfel: {e}")
                break
            except Exception as e:
                print(f"❌ Oväntat fel: {e}")
                break

    print(f"✅ Klart! {posts_collected} inlägg sparade till {output_file}")

if __name__ == "__main__":
    if len(TARGET_URL) > 5:
        scrape_thread(TARGET_URL)
    else:
        print("--- Flashback Trådskrapare ---")
        url_in = input("Klistra in URL till tråden (t.ex. https://www.flashback.org/t123456): ").strip()
        if url_in:
            scrape_thread(url_in)
        else:
            print("Ingen URL angiven. Avslutar.")
