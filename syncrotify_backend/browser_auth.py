import sys
import json
from pathlib import Path

def get_cookies_path(storage_root=None):
    root = Path(storage_root) if storage_root else Path.home() / ".syncrotify"
    return root / "cookies.json"

def extract_cookies(storage_root=None):
    from playwright.sync_api import sync_playwright

    root = Path(storage_root) if storage_root else Path.home() / ".syncrotify"
    print("Launching Browser for Authentication...")
    print("Please login to YouTube Music in the opened window.")
    print("Once logged in, the window will close automatically (or you can close it manually).")
    
    try:
        with sync_playwright() as p:
            # Launch chromium with stealth args
            # We use a persistent context (though here just launching browser with arguments)
            # to mimic a real user better and disable automation flags.
            browser = p.chromium.launch(
                headless=False,
                channel="chrome", # Try to use system chrome
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars"
                ],
                ignore_default_args=["--enable-automation"]
            )
            
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # Injection to hide webdriver property
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            page = context.new_page()
            
            try:
                page.goto("https://music.youtube.com", timeout=60000)
            except Exception as e:
                print(f"Navigation error: {e}")
                
            print("Waiting for login... (Please sign in)")
            
            # Wait for a sign of being logged in. 
            # e.g. avatar button or specific cookie "SAPISID" which indicates Google Auth.
            # We can loop and check cookies periodically.
            
            logged_in = False
            final_cookies = []
            
            for _ in range(60): 
                try:
                    # Check specific domain for login indicator
                    cookies_domain = context.cookies("https://music.youtube.com")
                    
                    has_sapisid = any(c['name'] == 'SAPISID' for c in cookies_domain)
                    has_secure = any(c['name'] == '__Secure-3PAPISID' for c in cookies_domain)
                    
                    if has_sapisid and has_secure:
                         print("Login detected! (SAPISID & __Secure-3PAPISID found)")
                         logged_in = True
                         # Capture ALL cookies immediately before window potentially closes
                         try:
                             final_cookies = context.cookies()
                         except:
                             # Fallback to what we just got
                             final_cookies = cookies_domain
                         break


                except Exception:
                    print("Browser window closed or disconnected.")
                    break
                
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                     break
            
            if not logged_in and not final_cookies:
                print("Login timed out or window closed before detection.")
                return False
            
            # Use captured cookies
            cookies = final_cookies
            
            # Deduplicate cookies by name
            # If multiple cookies have same name (diff domain/path), we should prioritize.
            # Usually strict dict construction takes last one. 
            # Browser cookies list might be in any order.
            # Ideally we want the one matching music.youtube.com best.
            # For now, let's just use a dict to remove exact name duplicates.
            cookie_dict = {}
            for c in cookies:
                cookie_dict[c['name']] = c['value']
            
            # Format for header
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
            
            # Find SAPISID
            sapisid = cookie_dict.get('SAPISID')
            
            try:
                browser.close()
            except: pass


            
            if not cookie_header:
                print("No cookies found.")
                return False

            # Generate Authorization Header
            auth_header_val = ""
            if sapisid:
                try:
                    import time
                    import hashlib
                    timestamp = str(int(time.time()))
                    origin = "https://music.youtube.com"
                    # SAPISIDHASH {timestamp}_{sha1(timestamp + " " + sapisid + " " + origin)}
                    raw_sig = f"{timestamp} {sapisid} {origin}"
                    sha1 = hashlib.sha1(raw_sig.encode("utf-8")).hexdigest()
                    auth_header_val = f"SAPISIDHASH {timestamp}_{sha1}"
                    print(f"Generated SAPISIDHASH: {auth_header_val}")
                except Exception as e:
                    print(f"Failed to generate SAPISIDHASH: {e}")
            else:
                 print("Warning: SAPISID cookie not found. Authorization header cannot be generated.")
                 # If SAPISID is missing, basic auth won't work well for ytmusicapi.
                 # We should probably abort or warn verify loudly.
                 print("Aborting header save - missing critical authentication cookie (SAPISID).")
                 return False

            # 1. Save Header JSON for ytmusicapi
            header_data = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Cookie": cookie_header,
                "Accept-Language": "en-US",
                "X-Goog-AuthUser": "0",
                "Origin": "https://music.youtube.com"
            }
            
            if auth_header_val:
                header_data["Authorization"] = auth_header_val
            
            headers_path = root / "headers_auth.json"
            headers_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(headers_path, "w") as f:
                json.dump(header_data, f, indent=4)
                
            print(f"Saved auth headers to {headers_path}")
            
            # 2. Save Netscape format for yt-dlp
            # Netscape format: domain, flag, path, secure, expiration, name, value
            cookies_txt_path = root / "cookies.txt"
            
            with open(cookies_txt_path, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# Generated by Syncrotify. Do not edit.\n\n")
                
                for c in cookies:
                    domain = c.get('domain', '')
                    flag = "TRUE" if domain.startswith('.') else "FALSE"
                    path = c.get('path', '/')
                    secure = "TRUE" if c.get('secure') else "FALSE"
                    expires = str(int(c.get('expires', 0))) # might be -1 if session?
                    name = c.get('name', '')
                    value = c.get('value', '')
                    
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
                    
            print(f"Saved Netscape cookies to {cookies_txt_path}")
            
            cookies_json_path = get_cookies_path(root)
            with open(cookies_json_path, "w") as f:
                json.dump({"cookie_header": cookie_header}, f)
                
            return True

    except Exception as e:
        print(f"Error: {e}")
        # Retrying with bundled chromium if chrome failed
        if "Executable doesn't exist" in str(e):
             print("Chrome not found, trying bundled Chromium...")
             # ... Logic to retry could go here, but for now simple script.
        input("Press Enter to exit...")
        return False

if __name__ == "__main__":
    success = extract_cookies()
