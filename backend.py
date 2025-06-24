from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from flask_cors import CORS
import logging
import time
import os
import google.generativeai as genai

# Setup Gemini API (Replace with your actual API key)
genai.configure(api_key="AIzaSyA5Uou2xAmjjpJRSMlj3_9mYqB9Fd83mZ4")

app = Flask(__name__)
CORS(app, supports_credentials=True)  # Enable CORS for frontend communication
log = logging.getLogger(__name__)

# Setup logging
def setup_logger():
    dt = time.strftime("%Y_%m_%d_%H_%M_%S")
    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    logging.basicConfig(
        filename=f'./logs/{dt}_JobEase.log',
        filemode='w',
        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.DEBUG
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    console_handler.setFormatter(console_format)
    logging.getLogger().addHandler(console_handler)

setup_logger()

class JobEaseBot:
    def __init__(self, username, password, job_role, work_type, location, experience):
        log.info("Initializing JobEase Bot...")
        self.username = username
        self.password = password
        self.job_role = job_role
        self.work_type = work_type
        self.location = location
        self.experience = experience
        self.blacklist = ["unpaid"]
        self.browser = self.setup_browser()
        self.wait = WebDriverWait(self.browser, 10)

    def setup_browser(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless")  # Remove this if you want to see the browser
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")

        browser = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
        return browser

    def login_to_linkedin(self):
        log.info("Logging in to LinkedIn...")
        self.browser.get("https://www.linkedin.com/login")
        time.sleep(2)  # Give time for the page to load

        try:
            username_field = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
            password_field = self.wait.until(EC.presence_of_element_located((By.ID, "password")))
            login_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@type="submit"]')))

            username_field.send_keys(self.username)
            password_field.send_keys(self.password)
            login_button.click()

            time.sleep(5)  # Wait for navigation
            log.info(f"Current URL after login: {self.browser.current_url}")

            if "feed" in self.browser.current_url:  # Check if redirected to homepage
                log.info("Login successful.")
                return True
            else:
                log.error("Login failed. Check credentials or CAPTCHA.")
                return False

        except Exception as e:
            log.error(f"Login failed: {e}")
            return False

    def search_jobs(self):
        log.info(f"Searching jobs for {self.job_role} in {self.location}...")
        try:
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={self.job_role}&location={self.location}&f_E={self.experience}"
            self.browser.get(search_url)
            log.info(f"Job search page loaded: {search_url}")

            return self.scrape_job_listings()
        except Exception as e:
            log.error(f"Error during job search: {e}")
            return []

    def scrape_job_listings(self):
        log.info("Scraping job listings...")
        jobs = []
        try:
            self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.jobs-search-results__list-item')))

            for _ in range(5):
                self.browser.execute_script("window.scrollBy(0, 1000);")
                time.sleep(1)

            job_cards = self.browser.find_elements(By.CSS_SELECTOR, '.jobs-search-results__list-item')
            for card in job_cards:
                try:
                    title = card.find_element(By.CSS_SELECTOR, '.job-card-list__title').text
                    company = card.find_element(By.CSS_SELECTOR, '.job-card-container__company-name').text
                    location = card.find_element(By.CSS_SELECTOR, '.job-card-container__metadata-item').text

                    if any(word in title.lower() or word in company.lower() for word in self.blacklist):
                        continue

                    jobs.append({'title': title, 'company': company, 'location': location})
                except Exception:
                    continue

            log.info(f"Found {len(jobs)} jobs.")
        except Exception as e:
            log.error(f"Error scraping jobs: {e}")

        return self.analyze_jobs_with_gemini(jobs)

    def analyze_jobs_with_gemini(self, jobs):
        log.info("Analyzing job descriptions using Gemini API...")
        refined_jobs = []
        for job in jobs:
            prompt = f"Analyze this job title and company to see if it's a good match for {self.job_role}: {job['title']} at {job['company']}. Provide a rating and brief reason."
            response = genai.generate_text(prompt)
            job['analysis'] = response if response else "No analysis available"
            refined_jobs.append(job)

        return refined_jobs

    def close_browser(self):
        log.info("Closing browser.")
        self.browser.quit()

@app.route('/start-bot', methods=['POST'])
def start_bot():
    data = request.json
    log.info(f"Received request: {data}")

    bot = JobEaseBot(
        data["username"], data["password"], data["job_role"], 
        data["work_type"], data.get("location", ""), data["experience"]
    )

    if not bot.login_to_linkedin():
        bot.close_browser()
        return jsonify({"error": "Login failed. Check credentials."}), 401

    jobs = bot.search_jobs()
    bot.close_browser()
    return jsonify({"jobs": jobs, "message": f"Found {len(jobs)} jobs!"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
