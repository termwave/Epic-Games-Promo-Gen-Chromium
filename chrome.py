import time
import os
import random
import string
import base64
import re
import gc
from enum import Enum
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from patchright.sync_api import sync_playwright
from colorama import Fore, Style, init
from bs4 import BeautifulSoup
import datetime

init(autoreset=True)
loaded_proxies = []
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

class LogLevel(Enum):
    DEBUG = 1
    INFO = 2
    WARNING = 3
    SUCCESS = 4
    ERROR = 5
    CRITICAL = 6
class Logger:
    def __init__(self, level: LogLevel = LogLevel.DEBUG):
        self.level = level
        self.prefix = "\033[38;5;176m[\033[38;5;97mtermwave\033[38;5;176m] "
        self.WHITE = "\u001b[37m"
        self.MAGENTA = "\033[38;5;97m"
        self.BRIGHT_MAGENTA = "\033[38;2;157;38;255m"
        self.LIGHT_CORAL = "\033[38;5;210m"
        self.RED = "\033[38;5;196m"
        self.GREEN = "\033[38;5;40m"
        self.YELLOW = "\033[38;5;220m"
        self.BLUE = "\033[38;5;21m"
        self.PINK = "\033[38;5;176m"
        self.CYAN = "\033[96m"
    def get_time(self):
        return datetime.datetime.now().strftime("%H:%M:%S")
    def _should_log(self, message_level: LogLevel) -> bool:
        return message_level.value >= self.level.value
    def _write(self, level_color, level_tag, message):
        print(f"{self.prefix}[{self.BRIGHT_MAGENTA}{self.get_time()}{self.PINK}] {self.PINK}[{level_color}{level_tag}{self.PINK}] -> {level_color}{message}{Style.RESET_ALL}")
    def info(self, message: str):
        if self._should_log(LogLevel.INFO):
            self._write(self.CYAN, "!", message)
    def success(self, message: str):
        if self._should_log(LogLevel.SUCCESS):
            self._write(self.GREEN, "Success", message)
    def warning(self, message: str):
        if self._should_log(LogLevel.WARNING):
            self._write(self.YELLOW, "Warning", message)
    def error(self, message: str):
        if self._should_log(LogLevel.ERROR):
            self._write(self.RED, "Error", message)
    def debug(self, message: str):
        if self._should_log(LogLevel.DEBUG):
            self._write(self.BLUE, "DEBUG", message)
    def failure(self, message: str):
        if self._should_log(LogLevel.ERROR):
            self._write(self.RED, "Failure", message)

log = Logger()

def human_delay(min_seconds=0.0, max_seconds=0.0):
    pass

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def human_typing(element, text, min_delay=0.0, max_delay=0.0):  
    element.focus()
    element.fill(text)

def get_email_from_file(filename="mails.txt"):
    if not os.path.exists(filename):
        raise FileNotFoundError(f"{filename} not found.")
    with open(filename, "r", encoding="utf-8") as file:
        lines = file.readlines()
    if not lines:
        raise ValueError("No emails left in mails.txt.")
    email = lines[0].strip()
    with open(filename, "w", encoding="utf-8") as file:
        file.writelines(lines[1:])  
    return email


def load_proxies(filename="proxy.txt"):
    global loaded_proxies
    loaded_proxies = []
    try:
        with open(filename, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                parts = line.split('@', 1)
                if len(parts) == 1 and line.count(':') == 3:
                    host, port, username, password = line.split(':')
                    loaded_proxies.append({
                        "server": f"http://{host}:{port}",
                        "username": username,
                        "password": password
                    })
                elif len(parts) == 2:
                    userpass, server = parts
                    user, pwd = userpass.split(":")
                    ip, port = server.split(":")
                    loaded_proxies.append({
                        "server": f"http://{ip}:{port}",
                        "username": user,
                        "password": pwd
                    })
                elif ':' in line:
                    ip, port = line.split(":")
                    loaded_proxies.append({"server": f"http://{ip}:{port}"})
        log.info(f"✅ Loaded {len(loaded_proxies)} proxies.")
    except Exception as e:
        log.warning(f"⚠️ Proxy load error: {e}")

def find_otp(email=None, timeout=300, interval=1):
    service = get_gmail_service()
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            results = service.users().messages().list(userId='me', q='is:unread').execute()
            messages = results.get('messages', [])
            for msg in messages:
                msg_id = msg['id']
                msg_data = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                headers = msg_data.get('payload', {}).get('headers', [])
                from_header = next((h['value'] for h in headers if h['name'] == 'From'), "")
                to_header = next((h['value'] for h in headers if h['name'] == 'To'), "")
                if "epicgames.com" not in from_header.lower():
                    continue
                if email and email.lower() not in to_header.lower():
                    continue
                payload = msg_data.get('payload', {})
                parts = payload.get('parts', [])
                def extract_otp_from_decoded(decoded):
                    soup = BeautifulSoup(decoded, "html.parser")
                    text = soup.get_text()
                    return re.search(r"\b\d{6}\b", text)
                for part in parts:
                    mime_type = part.get("mimeType")
                    body = part.get("body", {}).get("data")
                    if body:
                        decoded = base64.urlsafe_b64decode(body + '==').decode("utf-8", errors="ignore")
                        if mime_type == "text/html" or mime_type == "text/plain":
                            match = extract_otp_from_decoded(decoded)
                            if match:
                                service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                                return match.group()
                if not parts and "body" in payload:
                    body = payload["body"].get("data")
                    if body:
                        decoded = base64.urlsafe_b64decode(body + '==').decode("utf-8", errors="ignore")
                        match = extract_otp_from_decoded(decoded)
                        if match:
                            service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
                            return match.group()      
        except Exception as e:
            print(f"⚠️ Error while checking Gmail: {e}")
        time.sleep(interval)
    return None

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def input_verification_code(page, code):
    for i in range(6):
        field = page.locator(f"[name='code-input-{i}']")
        field.fill(code[i])

def register_and_get_promo():
 with sync_playwright() as p:
    browser = p.chromium.launch(
    headless=False,
    executable_path="C:\Program Files\Google\Chrome\Application\chrome.exe"
)
    context = browser.new_context(java_script_enabled=True)
    page = context.new_page()
    try:
        page.goto("https://www.epicgames.com/id/register/date-of-birth", wait_until="domcontentloaded")
        log.info(f"🕒 Loaded Date of Birth Page")
        page.locator("#month").click()
        page.locator(f"//li[@data-value='{random.randint(0,11)}']").click()
        page.locator("#day").click()
        page.locator(f"//li[@data-value='{random.randint(1,28)}']").click()
        human_typing(page.locator("#year"), str(random.randint(1980, 2005)))
        page.locator("#continue").click()
        page.wait_for_selector("#email")
        log.info(f"✅ Filled Date of Birth")
        email = get_email_from_file()
        log.info(f"✉️ Using {email}")
        if not email: raise Exception("Temp email failed")
        display_name = generate_random_string()
        log.info(f"🕒 Loaded Account Details Page")
        human_typing(page.locator("#email"), email)
        human_typing(page.locator("#name"), "Term")
        human_typing(page.locator("#lastName"), "Wave")
        human_typing(page.locator("#displayName"), display_name)
        human_typing(page.locator("#password"), email)
        page.locator("#tos").check()
        page.locator("#btn-submit").click()
        log.info(f"✅ Submitted Registration Form")
        page.wait_for_selector("input[name='code-input-0']", timeout=1000000)
        log.info("🔐 Waiting for OTP...")
        otp = find_otp(email)
        if not otp:
            browser.close()
            print("Failed to retrieve OTP.")
        log.info(f"🔐 OTP Fetched {otp}")
        input_verification_code(page, otp)
        page.locator("button:has-text('VERIFY')").click()
        log.success("🎉 OTP verified!")
        try:
            done_btn = page.locator("#link-success")
            done_btn.wait_for(state="visible", timeout=1000000)
            while not done_btn.is_enabled():
                time.sleep(0.5)
            page.goto("https://www.epicgames.com/account/personal", wait_until="domcontentloaded")
        except Exception as e:
            log.warning(f"⚠️ 'Done linking' button missing: {e}")
            page.wait_for_timeout(1000000)
        try:
            page.goto("https://store.epicgames.com/purchase?highlightColor=0078f2&offers=1-5f3c898b2a3244af99e9900e015717f8-da808af21c8e48cf854a3ada62bb1db6-&showNavigation=true", wait_until="domcontentloaded")
            log.info("🕒 Loaded corrective EULA page")
            accept_btn = page.locator('//*[@id="accept"]')
            accept_btn.wait_for(state="visible", timeout=1000000)
            while not accept_btn.is_enabled():
                time.sleep(0.5)
            accept_btn.click()
            log.info("✅ Clicked 'Accept' button (EULA)")
        except Exception as e:
            log.warning(f"⚠️ Accept button not clickable or missing: {e}")
        log.info("🕒 Waiting for checkout...")
        place_order_btn = page.locator("button:has-text('Place Order')")
        place_order_btn.wait_for(state="visible", timeout=1000000)
        while not place_order_btn.is_enabled():
            time.sleep(0.5)
        place_order_btn.click()
        log.info("🎯 Clicked 'Place Order'!")
        try:
            log.info("🕒 Checking if order is processing...")
            processing_detected = False
            for _ in range(900):
                try:
                    if "Processing" in page.locator("#purchase-app").inner_text():
                        log.info("🔄 'Processing - Please Wait.' detected")
                        processing_detected = True
                        break
                except:
                    pass
                    time.sleep(1)
            if not processing_detected:
                log.warning("⚠️ 'Processing' message not detected after 900 seconds.")
            blank_page_detected = False
            for _ in range(900):
                try:
                    if not page.locator("#purchase-app").inner_html().strip():
                        log.success("🎉 Order confirmed!")
                        blank_page_detected = True
                        break
                except:
                    pass
                    time.sleep(1)
            if not blank_page_detected:
                log.warning("⚠️ Blank page (order confirmation) not detected after 900 seconds.")
        except Exception as e:
                log.warning(f"⚠️ Order processing check failed: {e}")
    except Exception as e:
        log.failure(f"❌ Critical Error: {e}")
        raise e
    finally:
        try: context.close()
        except: pass
        try: browser.close()
        except: pass
        del page
        del context
        del browser
        gc.collect()

from pystyle import Center
import pyfiglet
banner = f'''
[+] Creator - Termwave
'''

def main():
    ultimate = pyfiglet.figlet_format("ULTIMATE", font="bloody")
    print("\n", Fore.CYAN + Center.XCenter(ultimate))
    print(Fore.CYAN + Center.XCenter(banner), "\n")
    get_gmail_service()
    load_proxies()
    register_and_get_promo()

if __name__ == "__main__":
    main()