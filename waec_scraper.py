"""
WAEC/NECO Question Scraper for myschool.ng
Run this on your local machine.

Install dependencies first:
    pip install requests beautifulsoup4

Usage:
    python waec_scraper.py
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}

BASE_URL = "https://myschool.ng/classroom"

def scrape_page(subject, exam_type, year, page=1):
    """Scrape a single page of questions"""
    url = f"{BASE_URL}/{subject}?exam_type={exam_type}&exam_year={year}&page={page}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  ✗ Page {page}: Status {response.status_code}")
            return None
        return response.text
    except Exception as e:
        print(f"  ✗ Page {page}: {e}")
        return None

def parse_questions(html, year, exam_type):
    """Extract questions from HTML - adjust selectors based on actual page structure"""
    soup = BeautifulSoup(html, 'html.parser')
    questions = []
    
    # This selector will need adjustment based on actual HTML structure
    # Run the test first to see what the HTML looks like
    question_blocks = soup.find_all('div', class_=re.compile(r'question|item'))
    
    for block in question_blocks:
        q = {
            'year': year,
            'exam_type': exam_type,
            'text': block.get_text(strip=True)[:500],  # First 500 chars
            'topic': None,  # To be filled by AI later
        }
        questions.append(q)
    
    return questions

def scrape_subject(subject, exam_type, start_year, end_year):
    """Scrape all years for a subject"""
    all_questions = []
    
    for year in range(start_year, end_year + 1):
        print(f"\n{exam_type.upper()} {year}...")
        page = 1
        year_questions = []
        
        while True:
            html = scrape_page(subject, exam_type, year, page)
            if not html:
                break
                
            questions = parse_questions(html, year, exam_type)
            if not questions:
                break
                
            year_questions.extend(questions)
            print(f"  ✓ Page {page}: {len(questions)} questions")
            
            page += 1
            time.sleep(1)  # Be polite - 1 second between requests
            
            if page > 20:  # Safety limit
                break
        
        all_questions.extend(year_questions)
        print(f"  Total for {year}: {len(year_questions)}")
    
    return all_questions

def test_connection():
    """Test if we can access the site"""
    print("Testing connection to myschool.ng...")
    url = f"{BASE_URL}/mathematics?exam_type=waec&exam_year=2023"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✓ Connection successful!\n")
            
            # Save raw HTML so you can inspect the structure
            with open("sample_page.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("Saved sample_page.html - open this to see the HTML structure")
            print("You'll need to adjust parse_questions() based on what you see.\n")
            
            # Show a preview
            soup = BeautifulSoup(response.text, 'html.parser')
            print("--- Text Preview (first 2000 chars) ---")
            print(soup.get_text()[:2000])
            return True
        else:
            print(f"✗ Failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    # Step 1: Test connection first
    if not test_connection():
        print("\nConnection failed. Try:")
        print("1. Check your internet connection")
        print("2. Try accessing the URL in your browser")
        print("3. They might be blocking your IP - try a VPN")
        return
    
    print("\n" + "="*50)
    print("Connection works! Next steps:")
    print("="*50)
    print("""
1. Open sample_page.html in your browser
2. Right-click → Inspect to see the HTML structure
3. Find the CSS selector for question blocks
4. Update parse_questions() with the correct selector
5. Uncomment the scraping code below and run again
    """)
    
    # Uncomment below once you've updated parse_questions()
    # -------------------------------------------------------
    # questions = scrape_subject(
    #     subject="mathematics",
    #     exam_type="waec", 
    #     start_year=2015,
    #     end_year=2024
    # )
    # 
    # with open("waec_math_questions.json", "w") as f:
    #     json.dump(questions, f, indent=2)
    # 
    # print(f"\nDone! Saved {len(questions)} questions to waec_math_questions.json")

if __name__ == "__main__":
    main()
