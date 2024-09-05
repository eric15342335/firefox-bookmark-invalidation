"""
Filter and display invalid websites URL from the
firefox bookmark json file.
"""
# Configuration
MAX_RETRIES = 3
TIMEOUT = 5
MAX_WORKERS = 20
NTP_SERVER = 'pool.ntp.org'
NTP_VERSION = 3
TIME_SYNC_THRESHOLD = 10
TERMINAL_UPDATE_THRESHOLD = 1
RESULTS_FILENAME = "website_test_results.json"

import json
import sys
import concurrent.futures
import cloudscraper
import tqdm
import colorama
from colorama import Fore, Style
import shutil
import os
from collections import defaultdict
import ntplib
from datetime import datetime, timezone
import requests
import re
import urllib.parse
import time

colorama.init(autoreset=True)  # Initialize colorama

def display_welcome_message():
    print(f"{Fore.CYAN}╔════════════════════════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║                  Welcome to Website URL Checker                ║")
    print(f"{Fore.CYAN}║                                                                ║")
    print(f"{Fore.CYAN}║  This application checks the validity of website URLs from     ║")
    print(f"{Fore.CYAN}║  your Firefox bookmarks JSON file.                             ║")
    print(f"{Fore.CYAN}║                                                                ║")
    print(f"{Fore.CYAN}║  It will test each URL and provide a summary of valid and      ║")
    print(f"{Fore.CYAN}║  invalid websites, along with detailed error information.      ║")
    print(f"{Fore.CYAN}╚════════════════════════════════════════════════════════════════╝")
    print()

def check_system_time():
    print(f"{Fore.CYAN}Checking system time...{Style.RESET_ALL}")
    try:
        ntp_client = ntplib.NTPClient()
        response = ntp_client.request(NTP_SERVER, version=NTP_VERSION)
        system_time = datetime.now(timezone.utc)
        ntp_time = datetime.fromtimestamp(response.tx_time, timezone.utc)
        time_diff = abs((system_time - ntp_time).total_seconds())
        
        print(f"NTP Server: {NTP_SERVER}")
        print(f"System time: {system_time}")
        print(f"NTP time: {ntp_time}")
        print(f"Time difference: {time_diff:.2f} seconds")
        
        if time_diff > TIME_SYNC_THRESHOLD:
            print(f"{Fore.YELLOW}Warning: Your system clock might be out of sync. Please consider synchronizing it.{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}System time is accurate.{Style.RESET_ALL}")
        time.sleep(2)
    except Exception as e:
        print(f"{Fore.YELLOW}Warning: Unable to check system time. Please ensure your system clock is accurate.{Style.RESET_ALL}")
        print(f"Detailed error message: {str(e)}")

def search_uri(data, depth=0):
    website_list = []
    if isinstance(data, dict):
        if 'uri' in data:
            website_list.append(data['uri'])
        if 'children' in data:
            website_list.extend(search_uri(data['children'], depth + 1))
    elif isinstance(data, list):
        for item in data:
            website_list.extend(search_uri(item, depth + 1))
    return list(set(website_list))  # Remove duplicates

def analyze_bookmarks(website_list):
    print(f"\n{Fore.CYAN}Analyzing bookmarks...{Style.RESET_ALL}")
    
    total_bookmarks = len(website_list)
    protocol_handlers = defaultdict(int)
    top_level_domains = defaultdict(int)
    
    for url in website_list:
        parsed_url = urllib.parse.urlparse(url)
        protocol_handlers[parsed_url.scheme] += 1
        tld = parsed_url.netloc.split('.')[-1]
        top_level_domains[tld] += 1
    
    print(f"Total bookmarks: {total_bookmarks}")
    
    print(f"\n{Fore.CYAN}Protocol handlers:{Style.RESET_ALL}")
    for protocol, count in sorted(protocol_handlers.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {protocol}: {count}")
    
    print(f"\n{Fore.CYAN}Top 5 Top-Level Domains:{Style.RESET_ALL}")
    for tld, count in sorted(top_level_domains.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  .{tld}: {count}")
    
    print(f"\n{Fore.CYAN}Other interesting statistics:{Style.RESET_ALL}")
    secure_urls = sum(1 for url in website_list if url.startswith('https://'))
    print(f"  Secure URLs (HTTPS): {secure_urls} ({secure_urls/total_bookmarks*100:.2f}%)")
    
    unique_domains = len(set(urllib.parse.urlparse(url).netloc for url in website_list))
    print(f"  Unique domains: {unique_domains}")
    
    print(f"\n{Fore.GREEN}Bookmark analysis complete. Starting URL testing...{Style.RESET_ALL}")
    time.sleep(2)

def test_url(url):
    scraper = cloudscraper.create_scraper()
    for _ in range(MAX_RETRIES):
        time.sleep(1)
        try:
            for method in ['get', 'head']:
                response = getattr(scraper, method)(url, timeout=TIMEOUT, allow_redirects=True, verify=True)
                if response.status_code < 400:
                    return True, None
        except requests.exceptions.SSLError:
            try:
                for method in ['get', 'head']:
                    response = getattr(scraper, method)(url, timeout=TIMEOUT, allow_redirects=True, verify=False)
                    if response.status_code < 400:
                        return True, None
            except Exception as e:
                return False, str(e)
        except Exception as e:
            return False, str(e)
    return False, f"Status code: {response.status_code}"

def process_websites(website_list):
    valid_websites = []
    invalid_websites = []
    update_buffer = []
    error_groups = defaultdict(list)

    terminal_width, terminal_height = shutil.get_terminal_size()

    def update_display():
        os.system('cls' if os.name == 'nt' else 'clear')  # Clear the screen
        half_height = terminal_height // 2

        output = []
        output.append(f"{Fore.CYAN}Valid websites:{Style.RESET_ALL}")
        valid_websites_display = valid_websites[-half_height+6:]  # Reserve one more line for the header
        output.extend([f"{Fore.GREEN}{url[:terminal_width-1]}{Style.RESET_ALL}" for url in valid_websites_display])
        output.append(f"{Fore.CYAN}{'-' * terminal_width}{Style.RESET_ALL}")
        output.append(f"{Fore.CYAN}Invalid websites (grouped by error):{Style.RESET_ALL}")

        remaining_lines = half_height - 5
        for error, urls in list(error_groups.items())[:remaining_lines//3]:
            output.append(f"{Fore.RED}{error}:{Style.RESET_ALL}")
            output.extend([f"  {Fore.YELLOW}{url[:terminal_width-3]}{Style.RESET_ALL}" for url in urls[-2:]])
            if len(urls) > 2:
                output.append(f"  {Fore.MAGENTA}... and {len(urls) - 2} more{Style.RESET_ALL}")
                remaining_lines -= 1
            output.append("")
            remaining_lines -= 3

        print('\n'.join(output))
    
    def group_error(error):
        # Remove URLs from error messages
        error = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '<URL>', error)
        
        # Group similar error messages
        if 'Connection' in error and 'timed out' in error:
            return 'Connection timed out'
        elif 'Name or service not known' in error:
            return 'Name or service not known'
        elif 'Max retries exceeded' in error:
            return 'Max retries exceeded'
        elif 'SSLError' in error:
            return 'SSL Error'
        elif 'ConnectionError' in error:
            return 'Connection Error'
        else:
            return error

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {executor.submit(test_url, url): url for url in website_list}
        try:
            for future in tqdm.tqdm(concurrent.futures.as_completed(future_to_url), total=len(website_list), desc="Testing websites", ncols=terminal_width):
                url = future_to_url[future]
                try:
                    is_valid, reason = future.result()
                    if is_valid:
                        valid_websites.append(url)
                    else:
                        invalid_websites.append((url, reason))
                        grouped_error = group_error(reason)
                        error_groups[grouped_error].append(url)
                except Exception as exc:
                    print(f"{Fore.RED}Error: {url} generated an exception: {exc}{Style.RESET_ALL}")
                    invalid_websites.append((url, str(exc)))
                    grouped_error = group_error(str(exc))
                    error_groups[grouped_error].append(url)
                
                update_buffer.append(url)
                if len(update_buffer) >= TERMINAL_UPDATE_THRESHOLD:
                    update_display()
                    update_buffer.clear()
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Stopping all jobs. Please wait...{Style.RESET_ALL}")
            executor.shutdown(wait=False, cancel_futures=True)
            print(f"{Fore.GREEN}All jobs stopped.{Style.RESET_ALL}")
            raise

    update_display()  # Final update
    return valid_websites, invalid_websites, error_groups

def main(jsonfile):
    display_welcome_message()  # Display welcome message
    check_system_time()  # Check system time before processing

    try:
        with open(jsonfile, 'r', encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print(f"{Fore.RED}Error: {jsonfile} is not a valid JSON file.{Style.RESET_ALL}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"{Fore.RED}Error: File {jsonfile} not found.{Style.RESET_ALL}")
        sys.exit(1)

    website_list = search_uri(data)
    analyze_bookmarks(website_list)  # Analyze bookmarks before testing
    try:
        start_time = time.time()
        valid_websites, invalid_websites, error_groups = process_websites(website_list)

        print(f"\n\n{Fore.CYAN}Summary:{Style.RESET_ALL}")
        print(f"Total websites: {Fore.MAGENTA}{len(website_list)}{Style.RESET_ALL}")
        print(f"Valid websites: {Fore.GREEN}{len(valid_websites)}{Style.RESET_ALL}")
        print(f"Invalid websites: {Fore.RED}{len(invalid_websites)}{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}Error distribution:{Style.RESET_ALL}")
        for error, urls in sorted(error_groups.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"{Fore.YELLOW}{error}: {Fore.RED}{len(urls)}{Style.RESET_ALL}")
            for url in urls[:5]:
                print(f"  {Fore.LIGHTBLACK_EX}{url}{Style.RESET_ALL}")
            if len(urls) > 5:
                print(f"  {Fore.LIGHTBLACK_EX}... and {len(urls) - 5} more{Style.RESET_ALL}")
            print()

        # Save results to a JSON file
        results = {
            "valid_websites": valid_websites,
            "invalid_websites": [{"url": url, "reason": reason} for url, reason in invalid_websites],
            "statistics": {
                "total": len(website_list),
                "valid": len(valid_websites),
                "invalid": len(invalid_websites),
                "error_distribution": {error: len(urls) for error, urls in error_groups.items()}
            }
        }
        
        with open(RESULTS_FILENAME, "w") as f:
            json.dump(results, f, indent=2)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print()
        print(f"{Fore.GREEN}┌───────────────────────────────────────────────────────────────┐{Style.RESET_ALL}")
        print(f"{Fore.GREEN}│                       Process Complete                        │{Style.RESET_ALL}")
        print(f"{Fore.GREEN}├───────────────────────────────────────────────────────────────┤{Style.RESET_ALL}")
        print(f"{Fore.GREEN}│ Detailed results have been saved to:                          │{Style.RESET_ALL}")
        print(f"{Fore.GREEN}│ {RESULTS_FILENAME:<61} │{Style.RESET_ALL}")
        print(f"{Fore.GREEN}├───────────────────────────────────────────────────────────────┤{Style.RESET_ALL}")
        print(f"{Fore.GREEN}│ Time elapsed: {elapsed_time:.2f} seconds                              │{Style.RESET_ALL}")
        print(f"{Fore.GREEN}└───────────────────────────────────────────────────────────────┘{Style.RESET_ALL}")
        print()

    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Program interrupted by user. Exiting...{Style.RESET_ALL}")
        sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"{Fore.RED}Usage: python {sys.argv[0]} <jsonfile>{Style.RESET_ALL}")
        sys.exit(1)
    main(sys.argv[1])
