#!/usr/bin/env python3
"""
Debug script to test device unclaim process - Complete Version
"""

import logging
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import os
import tempfile
import shutil
import uuid
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UnclaimDebugger:
    """Debug the unclaim process"""
    
    def __init__(self, username: str, password: str, org_name: str, device_serial: str, headless: bool = False):
        self.username = username
        self.password = password
        self.org_name = org_name
        self.device_serial = device_serial
        self.headless = headless
        self.driver = None
        self.wait = None
        self.temp_dir = None
        
    def __enter__(self):
        self.setup_driver()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass
    
    def setup_driver(self):
        """Setup Chrome driver"""
        options = webdriver.ChromeOptions()
        
        # Create unique user data directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        random_id = str(uuid.uuid4())[:8]
        self.temp_dir = os.path.join(
            tempfile.gettempdir(), 
            f'meraki_unclaim_debug_{timestamp}_{random_id}'
        )
        
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, mode=0o700)
        
        # Core options
        options.add_argument(f'--user-data-dir={self.temp_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        if self.headless:
            options.add_argument('--headless=new')
            options.add_argument('--window-size=1920,1080')
            logger.info("Running in HEADLESS mode")
        else:
            options.add_argument('--window-size=1920,1080')
            logger.info("Running in GUI mode")
        
        # Additional options for stability
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-setuid-sandbox')
        
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 30)
        logger.info("Chrome driver initialized")
    
    def save_debug_info(self, step: str):
        """Save screenshot and page source for debugging"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Screenshot
        screenshot_file = f"unclaim_debug_{step}_{timestamp}.png"
        self.driver.save_screenshot(screenshot_file)
        logger.info(f"Screenshot saved: {screenshot_file}")
        
        # Page source
        source_file = f"unclaim_debug_{step}_{timestamp}.html"
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        logger.info(f"Page source saved: {source_file}")
        
        # Current URL
        logger.info(f"Current URL: {self.driver.current_url}")
    
    def login(self):
        """Login to Meraki Dashboard with 2FA support"""
        logger.info("Logging in...")
        self.driver.get("https://dashboard.meraki.com")
        time.sleep(3)
        
        # Step 1: Enter email
        logger.info("Step 1: Entering email")
        email_field = None
        email_selectors = [
            (By.ID, "email"),
            (By.ID, "Email"),
            (By.NAME, "email"),
            (By.CSS_SELECTOR, "input[type='email']")
        ]
        
        for selector_type, selector_value in email_selectors:
            try:
                email_field = self.wait.until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.info(f"Found email field with {selector_type}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not email_field:
            raise Exception("Could not find email field")
        
        email_field.send_keys(self.username)
        email_field.send_keys(Keys.RETURN)
        time.sleep(3)
        
        # Step 2: Enter password - try both lowercase and uppercase
        logger.info("Step 2: Entering password")
        password_field = None
        password_selectors = [
            (By.ID, "Password"),  # Capital P first since that's what you have
            (By.ID, "password"),
            (By.NAME, "Password"),
            (By.NAME, "password"),
            (By.CSS_SELECTOR, "input[type='password']")
        ]
        
        for selector_type, selector_value in password_selectors:
            try:
                password_field = self.wait.until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.info(f"Found password field with {selector_type}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not password_field:
            self.save_debug_info("login_no_password_field")
            raise Exception("Could not find password field")
        
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)
        
        # Step 3: Handle 2FA
        logger.info("Step 3: Checking for 2FA...")
        time.sleep(5)
        
        # Look for verification code field
        verification_field = None
        verification_selectors = [
            (By.ID, "code"),
            (By.ID, "Code"),
            (By.ID, "verification-code"),
            (By.ID, "verificationCode"),
            (By.NAME, "code"),
            (By.NAME, "Code"),
            (By.CSS_SELECTOR, "input[type='text'][placeholder*='code' i]"),
            (By.CSS_SELECTOR, "input[type='text'][placeholder*='verification' i]"),
            (By.CSS_SELECTOR, "input[type='number']"),
            (By.XPATH, "//input[@type='text' or @type='number']")
        ]
        
        for selector_type, selector_value in verification_selectors:
            try:
                # Look for all matching elements
                elements = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located((selector_type, selector_value))
                )
                # Find the first visible input that's not email/password
                for elem in elements:
                    if elem.is_displayed():
                        elem_type = elem.get_attribute('type')
                        elem_id = (elem.get_attribute('id') or '').lower()
                        elem_name = (elem.get_attribute('name') or '').lower()
                        # Skip if it's email or password field
                        if elem_type != 'password' and 'email' not in elem_id and 'email' not in elem_name:
                            verification_field = elem
                            logger.info(f"Found verification field with {selector_type}='{selector_value}'")
                            break
                if verification_field:
                    break
            except TimeoutException:
                continue
        
        if verification_field:
            logger.info("=" * 60)
            logger.info("2FA VERIFICATION REQUIRED")
            logger.info("=" * 60)
            logger.info("Please check your email for the verification code.")
            
            # Always prompt for code
            verification_code = input("Enter verification code: ").strip()
            
            if verification_code:
                verification_field.clear()
                verification_field.send_keys(verification_code)
                
                # Find and click submit button
                submit_clicked = False
                submit_selectors = [
                    (By.XPATH, "//button[contains(text(), 'Verify')]"),
                    (By.XPATH, "//button[contains(text(), 'Submit')]"),
                    (By.XPATH, "//button[contains(text(), 'Continue')]"),
                    (By.XPATH, "//button[contains(text(), 'Sign in')]"),
                    (By.XPATH, "//button[contains(text(), 'Log in')]"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                    (By.XPATH, "//button")  # Any button as last resort
                ]
                
                for selector_type, selector_value in submit_selectors:
                    try:
                        buttons = self.driver.find_elements(selector_type, selector_value)
                        for btn in buttons:
                            if btn.is_displayed() and btn.is_enabled():
                                logger.info(f"Clicking button: {btn.text}")
                                btn.click()
                                submit_clicked = True
                                break
                        if submit_clicked:
                            break
                    except Exception:
                        continue
                
                if not submit_clicked:
                    logger.info("No submit button found, pressing Enter")
                    verification_field.send_keys(Keys.RETURN)
                
                logger.info("Submitted verification code")
                time.sleep(10)  # Wait for verification to process
        else:
            logger.info("No 2FA field detected automatically")
            logger.info("If you see a verification field, please complete it manually")
            input("Press Enter after completing any 2FA requirements...")
        
        # Step 4: Wait for dashboard to load
        logger.info("Step 4: Waiting for dashboard to load...")
        dashboard_loaded = False
        dashboard_selectors = [
            (By.CLASS_NAME, "main-navigation"),
            (By.CLASS_NAME, "nav-bar"),
            (By.XPATH, "//span[text()='Organization']"),
            (By.XPATH, "//a[contains(@href, '/organization')]")
        ]
        
        # Try multiple times with longer timeout
        for attempt in range(3):
            for selector_type, selector_value in dashboard_selectors:
                try:
                    WebDriverWait(self.driver, 20).until(
                        EC.presence_of_element_located((selector_type, selector_value))
                    )
                    dashboard_loaded = True
                    logger.info(f"Dashboard loaded! Found: {selector_type}='{selector_value}'")
                    break
                except TimeoutException:
                    continue
            
            if dashboard_loaded:
                break
            else:
                logger.info(f"Dashboard not loaded yet, attempt {attempt + 1}/3")
                time.sleep(5)
        
        if not dashboard_loaded:
            self.save_debug_info("login_failed_no_dashboard")
            raise Exception("Dashboard did not load after login")
        
        logger.info("Login completed successfully!")
        self.save_debug_info("after_login")
    
    def select_organization(self, org_name: str):
        """Select organization by name"""
        logger.info(f"Selecting organization: {org_name}")
        
        # Check if we're on the organizations overview page
        current_url = self.driver.current_url
        logger.info(f"Current URL: {current_url}")
        
        if "/organizations" in current_url or "global_overview" in current_url:
            logger.info("On organizations overview page - looking for org in table")
            
            # Try to find the organization in the table
            org_found = False
            
            # Method 1: Click on organization link in table
            org_link_selectors = [
                (By.LINK_TEXT, org_name),
                (By.PARTIAL_LINK_TEXT, org_name),
                (By.XPATH, f"//a[contains(text(), '{org_name}')]"),
                (By.XPATH, f"//a[contains(., '{org_name}')]"),
                (By.XPATH, f"//td[contains(text(), '{org_name}')]//a"),
                (By.XPATH, f"//tr[contains(., '{org_name}')]//a"),
                # For table rows that might have the org name in a cell
                (By.XPATH, f"//td[contains(text(), '{org_name}')]/preceding-sibling::td//a"),
                (By.XPATH, f"//td[contains(text(), '{org_name}')]/following-sibling::td//a"),
            ]
            
            for method, selector in org_link_selectors:
                try:
                    logger.info(f"Trying to find org with: {method} = '{selector}'")
                    org_element = self.wait.until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    logger.info(f"Found organization element: {org_element.text}")
                    org_element.click()
                    org_found = True
                    logger.info(f"Clicked on organization: {org_name}")
                    break
                except Exception as e:
                    logger.debug(f"Method {method} failed: {e}")
                    continue
            
            if not org_found:
                logger.error(f"Could not find organization '{org_name}' in the table")
                self.save_debug_info("org_not_found_in_table")
                
                # List visible organizations for debugging
                try:
                    org_links = self.driver.find_elements(By.CSS_SELECTOR, "table a")
                    logger.info(f"Found {len(org_links)} links in table:")
                    for link in org_links[:10]:  # First 10
                        if link.text.strip():
                            logger.info(f"  - {link.text.strip()}")
                except Exception:
                    pass
                
                return False
            
            # Wait for page to load after clicking
            time.sleep(5)
            
            # Verify we're now in the organization
            new_url = self.driver.current_url
            logger.info(f"New URL after org selection: {new_url}")
            
            return True
            
        else:
            # We might already be in an organization, need to switch
            logger.info("Not on organizations overview - looking for org switcher")
            
            # Click org selector dropdown
            org_selector = None
            org_selector_methods = [
                (By.CLASS_NAME, "org-selector"),
                (By.CSS_SELECTOR, ".org-selector"),
                (By.CSS_SELECTOR, "[class*='org-selector']"),
                (By.XPATH, "//div[contains(@class, 'org-selector')]"),
                (By.XPATH, "//button[contains(@class, 'org-selector')]"),
                # Look for the organization name in the header
                (By.XPATH, f"//div[contains(@class, 'header')]//span[contains(text(), 'Organization')]"),
                (By.XPATH, "//button[contains(., 'Organization')]"),
            ]
            
            for method, selector in org_selector_methods:
                try:
                    org_selector = self.wait.until(EC.element_to_be_clickable((method, selector)))
                    logger.info(f"Found org selector with: {method} = {selector}")
                    break
                except TimeoutException:
                    logger.debug(f"Org selector not found with: {method} = {selector}")
                    continue
            
            if not org_selector:
                logger.error("Could not find organization selector dropdown")
                self.save_debug_info("no_org_selector")
                return False
            
            org_selector.click()
            time.sleep(2)
            self.save_debug_info("after_org_selector_click")
            
            # Find and click org in dropdown
            org_found = False
            org_name_methods = [
                (By.CLASS_NAME, "org-name"),
                (By.CSS_SELECTOR, ".org-name"),
                (By.XPATH, f"//span[contains(text(), '{org_name}')]"),
                (By.XPATH, f"//div[contains(text(), '{org_name}')]"),
                (By.XPATH, f"//*[contains(text(), '{org_name}')]")
            ]
            
            for method, selector in org_name_methods:
                try:
                    org_elements = self.driver.find_elements(method, selector)
                    logger.info(f"Found {len(org_elements)} org elements with: {method} = {selector}")
                    
                    for elem in org_elements:
                        if org_name.lower() in elem.text.lower():
                            elem.click()
                            logger.info(f"Clicked on organization: {elem.text}")
                            org_found = True
                            break
                    
                    if org_found:
                        break
                except Exception as e:
                    logger.debug(f"Error with {method} = {selector}: {e}")
            
            if not org_found:
                logger.error(f"Could not find organization '{org_name}' in dropdown")
                self.save_debug_info("org_not_found_in_dropdown")
                return False
            
            time.sleep(3)
            return True
    
    def select_organization_by_id(self, org_id: str):
        """Select organization by ID when on the organizations table page"""
        logger.info(f"Looking for organization with ID: {org_id}")
        
        # On the organizations page, we need to find the row with this org ID
        # The org ID might be in a cell, and we need to click the org name link in the same row
        
        try:
            # Method 1: Find the row containing the org ID and click the link in that row
            row_selectors = [
                f"//tr[contains(., '{org_id}')]//a",
                f"//td[contains(text(), '{org_id}')]/parent::tr//a",
                f"//td[text()='{org_id}']/parent::tr//a",
                # Sometimes the ID might be in a different column
                f"//tr[td[contains(text(), '{org_id}')]]//a[1]",
            ]
            
            for selector in row_selectors:
                try:
                    logger.info(f"Trying selector: {selector}")
                    org_link = self.wait.until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    org_name = org_link.text
                    logger.info(f"Found organization: {org_name} (ID: {org_id})")
                    org_link.click()
                    logger.info(f"Clicked on organization: {org_name}")
                    return True
                except Exception as e:
                    logger.debug(f"Selector failed: {e}")
                    continue
            
            # If direct selection didn't work, try to find the org by looking at the page structure
            logger.info("Direct selection failed, analyzing page structure...")
            
            # Get all table rows
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, table tr")
            logger.info(f"Found {len(rows)} table rows")
            
            for row in rows:
                row_text = row.text
                if org_id in row_text:
                    logger.info(f"Found org ID in row: {row_text[:100]}...")
                    # Try to find and click the first link in this row
                    try:
                        link = row.find_element(By.TAG_NAME, "a")
                        logger.info(f"Found link in row: {link.text}")
                        link.click()
                        return True
                    except Exception as e:
                        logger.debug(f"Could not find/click link in row: {e}")
            
            logger.error(f"Could not find organization with ID {org_id}")
            self.save_debug_info("org_id_not_found")
            return False
            
        except Exception as e:
            logger.error(f"Error selecting organization by ID: {e}")
            return False
    
    def debug_unclaim_process(self):
        """Step through the unclaim process with debugging"""
        try:
            # Step 1: Select organization
            logger.info(f"Step 1: Selecting organization '{self.org_name}'")
            self.save_debug_info("1_before_org_select")
            
            # Check if org_name is numeric (org ID) or text (org name)
            if self.org_name.isdigit():
                logger.info(f"Organization appears to be an ID: {self.org_name}")
                # For org IDs, we need to look in the table differently
                if not self.select_organization_by_id(self.org_name):
                    return False
            else:
                if not self.select_organization(self.org_name):
                    return False
            
            time.sleep(3)
            self.save_debug_info("2_after_org_select")
            
            # Step 2: Navigate to Organization > Inventory
            logger.info("Step 2: Navigating to Organization > Inventory")
            
            # Check if we're already on an organization page
            current_url = self.driver.current_url
            if "/organization/" in current_url:
                logger.info("Already in organization context, trying direct navigation to inventory")
                
                # Method 1: Try direct URL navigation
                try:
                    # Extract the organization part from current URL
                    # URL format: https://n109.meraki.com/o/tSDYWdTb/manage/organization/summary
                    url_parts = current_url.split('/manage/')
                    if len(url_parts) > 1:
                        base_url = url_parts[0]
                        inventory_url = f"{base_url}/manage/organization/inventory"
                        logger.info(f"Navigating directly to: {inventory_url}")
                        self.driver.get(inventory_url)
                        time.sleep(5)
                        
                        # Check if we made it to inventory
                        if "/inventory" in self.driver.current_url:
                            logger.info("Successfully navigated to inventory page")
                            self.save_debug_info("4_inventory_page")
                        else:
                            logger.warning("Direct navigation didn't reach inventory page")
                except Exception as e:
                    logger.error(f"Direct navigation failed: {e}")
            
            # If direct navigation didn't work or we're not on org page, try finding menu
            if "/inventory" not in self.driver.current_url:
                logger.info("Attempting to find Organization menu...")
                
                # Try different ways to find Organization menu or Inventory link
                menu_found = False
                menu_methods = [
                    # Direct inventory link
                    (By.XPATH, "//a[contains(text(), 'Inventory')]"),
                    (By.XPATH, "//a[contains(@href, '/inventory')]"),
                    (By.LINK_TEXT, "Inventory"),
                    (By.PARTIAL_LINK_TEXT, "Inventory"),
                    # Organization menu items
                    (By.XPATH, "//span[text()='Organization']"),
                    (By.XPATH, "//span[contains(text(), 'Organization')]"),
                    (By.XPATH, "//a[contains(text(), 'Organization')]"),
                    (By.XPATH, "//button[contains(text(), 'Organization')]"),
                    # Navigation patterns
                    (By.XPATH, "//nav//span[contains(text(), 'Organization')]"),
                    (By.XPATH, "//div[@class='main-navigation']//span[text()='Organization']"),
                    # Menu items
                    (By.CSS_SELECTOR, "[class*='nav'][class*='organization']"),
                    (By.CSS_SELECTOR, "span.nav-item-label"),
                    # Sidebar patterns
                    (By.XPATH, "//aside//span[contains(text(), 'Organization')]"),
                    (By.CSS_SELECTOR, "[class*='sidebar'] [class*='organization']")
                ]
                
                for method, selector in menu_methods:
                    try:
                        element = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        logger.info(f"Found element with: {method} = {selector}")
                        
                        # If it's directly an inventory link, click it
                        if "Inventory" in element.text or "inventory" in (element.get_attribute('href') or ''):
                            element.click()
                            menu_found = True
                            logger.info("Clicked on Inventory link")
                            break
                        # If it's Organization menu, click it first
                        elif "Organization" in element.text:
                            element.click()
                            logger.info("Clicked on Organization menu")
                            time.sleep(2)
                            
                            # Now look for Inventory submenu
                            inventory_link = self.wait.until(
                                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
                            )
                            inventory_link.click()
                            menu_found = True
                            logger.info("Clicked on Inventory submenu")
                            break
                    except TimeoutException:
                        continue
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {e}")
                        continue
                
                if not menu_found:
                    logger.error("Could not find Organization menu or Inventory link")
                    self.save_debug_info("2_no_menu_found")
                    
                    # List all links on the page for debugging
                    try:
                        all_links = self.driver.find_elements(By.TAG_NAME, "a")
                        logger.info(f"Found {len(all_links)} links on page:")
                        for link in all_links[:20]:  # First 20 links
                            href = link.get_attribute('href') or ''
                            text = link.text.strip()
                            if text or 'inventory' in href.lower() or 'organization' in href.lower():
                                logger.info(f"  Link: text='{text}', href='{href}'")
                    except Exception as e:
                        logger.debug(f"Error listing links: {e}")
                    
                    return False
            
            # Wait for inventory page to load
            time.sleep(5)
            
            # Verify we're on the inventory page
            if "/inventory" not in self.driver.current_url:
                logger.error("Failed to navigate to inventory page")
                self.save_debug_info("navigation_failed")
                return False
            
            logger.info("Successfully navigated to inventory page")
            self.save_debug_info("4_inventory_page")
            
            # Step 3: Search for device
            logger.info(f"Step 3: Searching for device {self.device_serial}")
            
            # Find search box
            search_box = None
            search_methods = [
                (By.CLASS_NAME, "search-box"),
                (By.CSS_SELECTOR, "input[type='search']"),
                (By.CSS_SELECTOR, "input[placeholder*='Search']"),
                (By.CSS_SELECTOR, "input[placeholder*='search']"),
                (By.XPATH, "//input[@type='search']"),
                (By.XPATH, "//input[contains(@placeholder, 'Search')]")
            ]
            
            for method, selector in search_methods:
                try:
                    search_box = self.wait.until(EC.presence_of_element_located((method, selector)))
                    logger.info(f"Found search box with: {method} = {selector}")
                    break
                except TimeoutException:
                    logger.debug(f"Search box not found with: {method} = {selector}")
                    continue
            
            if not search_box:
                logger.error("Could not find search box")
                self.save_debug_info("4_no_search_box")
                
                # List all input elements for debugging
                inputs = self.driver.find_elements(By.TAG_NAME, "input")
                logger.info(f"Found {len(inputs)} input elements:")
                for i, inp in enumerate(inputs[:10]):  # First 10 only
                    logger.info(f"  Input {i}: type={inp.get_attribute('type')}, "
                              f"placeholder={inp.get_attribute('placeholder')}, "
                              f"class={inp.get_attribute('class')}")
                return False
            
            search_box.clear()
            search_box.send_keys(self.device_serial)
            search_box.send_keys(Keys.RETURN)
            time.sleep(3)
            self.save_debug_info("5_after_search")
            
            # Step 4: Select device checkbox
            logger.info("Step 4: Selecting device checkbox")
            
            # Wait a bit for search results to fully load
            time.sleep(3)
            
            # Find checkbox - the checkbox appears to be in the first cell of the row containing the serial
            checkbox = None
            checkbox_methods = [
                # First try the most specific - checkbox in first cell of row with serial
                (By.XPATH, f"//tr[contains(.,'{self.device_serial}')]/td[1]//input[@type='checkbox']"),
                # Standard methods
                (By.XPATH, f"//tr[contains(.,'{self.device_serial}')]//input[@type='checkbox']"),
                (By.XPATH, f"//td[contains(text(),'{self.device_serial}')]/preceding-sibling::td//input[@type='checkbox']"),
                (By.XPATH, f"//td[contains(text(),'{self.device_serial}')]/parent::tr//input[@type='checkbox']"),
                (By.XPATH, f"//td[text()='{self.device_serial}']/parent::tr//input[@type='checkbox']"),
                (By.XPATH, f"//input[@type='checkbox' and ancestor::tr[contains(., '{self.device_serial}')]]"),
                # Look for checkbox in the same row as the serial
                (By.XPATH, f"//tr[contains(td, '{self.device_serial}')]//input[@type='checkbox']"),
                # Sometimes the checkbox might be before the serial in the DOM
                (By.XPATH, f"//tr[.//text()[contains(., '{self.device_serial}')]]//input[@type='checkbox']")
            ]
            
            for method, selector in checkbox_methods:
                try:
                    checkbox = self.wait.until(EC.element_to_be_clickable((method, selector)))
                    logger.info(f"Found checkbox with: {method} = {selector}")
                    break
                except TimeoutException:
                    logger.debug(f"Checkbox not found with: {method} = {selector}")
                    continue
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            if not checkbox:
                logger.error("Could not find device checkbox with specific selectors")
                self.save_debug_info("5_no_checkbox")
                
                # Try a different approach - if there's only one device in search results
                logger.info("Trying alternative approach - checking visible checkboxes")
                
                # Get all visible checkboxes that are not header checkboxes
                all_checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                logger.info(f"Found {len(all_checkboxes)} total checkboxes")
                
                # Debug: Log information about each checkbox
                for idx, cb in enumerate(all_checkboxes):
                    try:
                        # Try multiple ways to get parent row
                        parent_row = None
                        
                        # Method 1: Direct ancestor
                        try:
                            parent_row = cb.find_element(By.XPATH, "./ancestor::tr")
                        except:
                            # Method 2: Go up through parents
                            try:
                                parent = cb.find_element(By.XPATH, "./..")
                                while parent and parent.tag_name != "tr":
                                    parent = parent.find_element(By.XPATH, "./..")
                                parent_row = parent
                            except:
                                pass
                        
                        if parent_row:
                            row_text = parent_row.text[:200]
                            logger.info(f"Checkbox {idx}: Row text = '{row_text}'")
                            logger.info(f"  Contains serial '{self.device_serial}': {self.device_serial in parent_row.text}")
                            logger.info(f"  Checkbox displayed: {cb.is_displayed()}")
                            logger.info(f"  Checkbox enabled: {cb.is_enabled()}")
                            
                            # If this is the device row, try to click it
                            if self.device_serial in parent_row.text and cb.is_displayed():
                                logger.info(f"Found checkbox for device! Attempting to click...")
                                try:
                                    cb.click()
                                    logger.info("Successfully clicked checkbox")
                                    checkbox = cb
                                    break
                                except Exception as click_error:
                                    logger.error(f"Failed to click checkbox: {click_error}")
                                    # Try JavaScript click
                                    try:
                                        self.driver.execute_script("arguments[0].click();", cb)
                                        logger.info("Successfully clicked checkbox using JavaScript")
                                        checkbox = cb
                                        break
                                    except Exception as js_error:
                                        logger.error(f"JavaScript click also failed: {js_error}")
                        else:
                            logger.info(f"Checkbox {idx}: Could not find parent row")
                            
                    except Exception as e:
                        logger.error(f"Error analyzing checkbox {idx}: {e}")
                
                if not checkbox:
                    # Last resort: Try to find by position if there's only one data row
                    logger.info("Last resort: Looking for data rows")
                    all_rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, table tr")
                    data_rows = []
                    
                    for row in all_rows:
                        if self.device_serial in row.text:
                            data_rows.append(row)
                            logger.info(f"Found data row: {row.text[:100]}")
                    
                    if len(data_rows) == 1:
                        # Try to find checkbox in this row
                        row_checkboxes = data_rows[0].find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                        if row_checkboxes:
                            logger.info(f"Found {len(row_checkboxes)} checkboxes in device row")
                            try:
                                row_checkboxes[0].click()
                                logger.info("Clicked first checkbox in device row")
                                checkbox = row_checkboxes[0]
                            except Exception as e:
                                logger.error(f"Failed to click row checkbox: {e}")
                                # Try JavaScript
                                try:
                                    self.driver.execute_script("arguments[0].click();", row_checkboxes[0])
                                    logger.info("Clicked using JavaScript")
                                    checkbox = row_checkboxes[0]
                                except Exception as js_e:
                                    logger.error(f"JavaScript click failed: {js_e}")
                
                if not checkbox:
                    logger.error("Failed to find or click any checkbox")
                    return False
            
            if checkbox:
                logger.info("Clicking device checkbox")
                checkbox.click()
                time.sleep(2)
                self.save_debug_info("6_after_checkbox")
            else:
                logger.error("Failed to find and click checkbox")
                return False
            
            # Step 5: Click Unclaim button
            logger.info("Step 5: Looking for Unclaim button")
            
            # First, let's see what buttons are available
            logger.info("Analyzing available buttons after checkbox selection...")
            all_buttons = self.driver.find_elements(By.TAG_NAME, "button")
            visible_buttons = [btn for btn in all_buttons if btn.is_displayed()]
            logger.info(f"Found {len(visible_buttons)} visible buttons:")
            
            for i, btn in enumerate(visible_buttons[:20]):  # Show up to 20 buttons
                btn_text = btn.text.strip()
                if btn_text:  # Only show buttons with text
                    logger.info(f"  Button {i}: '{btn_text}'")
            
            # Also check for links that might act as buttons
            all_links = self.driver.find_elements(By.TAG_NAME, "a")
            action_links = [link for link in all_links if link.is_displayed() and 
                          any(word in link.text.lower() for word in ['unclaim', 'remove', 'delete', 'unassign'])]
            
            if action_links:
                logger.info(f"Found {len(action_links)} action links:")
                for i, link in enumerate(action_links[:10]):
                    logger.info(f"  Link {i}: '{link.text}'")
            
            # Check if there's a disabled button that needs to be enabled
            disabled_buttons = [btn for btn in all_buttons if not btn.is_enabled() and btn.is_displayed()]
            if disabled_buttons:
                logger.info(f"Found {len(disabled_buttons)} disabled buttons:")
                for i, btn in enumerate(disabled_buttons[:5]):
                    if btn.text:
                        logger.info(f"  Disabled button {i}: '{btn.text}'")
            
            # Now try to find the Unclaim button with various methods
            unclaim_btn = None
            unclaim_methods = [
                # Standard button searches
                (By.XPATH, "//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[contains(., 'Unclaim')]"),
                (By.XPATH, "//button[contains(text(), 'unclaim')]"),  # lowercase
                (By.XPATH, "//button[contains(text(), 'UNCLAIM')]"),  # uppercase
                (By.XPATH, "//button[contains(@class, 'unclaim')]"),
                (By.XPATH, "//a[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[text()='Unclaim']"),
                # Alternative texts
                (By.XPATH, "//button[contains(text(), 'Remove')]"),
                (By.XPATH, "//button[contains(text(), 'Delete')]"),
                (By.XPATH, "//button[contains(text(), 'Unassign')]"),
                # Look in toolbars and action areas
                (By.XPATH, "//div[contains(@class, 'toolbar')]//button"),
                (By.XPATH, "//div[contains(@class, 'actions')]//button"),
                (By.XPATH, "//div[contains(@class, 'bulk')]//button"),
                # Sometimes it's an icon button with tooltip
                (By.XPATH, "//button[@title='Unclaim']"),
                (By.XPATH, "//button[@aria-label='Unclaim']"),
                # Span inside button
                (By.XPATH, "//button[span[contains(text(), 'Unclaim')]]"),
                # Any element with unclaim text that's clickable
                (By.XPATH, "//*[contains(text(), 'Unclaim') and not(self::script)]"),
            ]
            
            # Try multiple times as button might appear dynamically
            for attempt in range(3):
                for method, selector in unclaim_methods:
                    try:
                        elements = self.driver.find_elements(method, selector)
                        for elem in elements:
                            if elem.is_displayed() and elem.is_enabled():
                                elem_text = elem.text.strip() or elem.get_attribute('title') or elem.get_attribute('aria-label') or ''
                                logger.info(f"Found potential unclaim element: '{elem_text}' with {method}")
                                
                                # Check if it's actually an unclaim/remove button
                                if any(word in elem_text.lower() for word in ['unclaim', 'remove', 'delete', 'unassign']):
                                    unclaim_btn = elem
                                    logger.info(f"Selected unclaim button: '{elem_text}'")
                                    break
                        
                        if unclaim_btn:
                            break
                            
                    except Exception as e:
                        logger.debug(f"Error with selector {selector}: {e}")
                        continue
                
                if unclaim_btn:
                    break
                else:
                    logger.info(f"Unclaim button not found, attempt {attempt + 1}/3")
                    
                    # Try clicking the checkbox again in case it didn't register
                    if attempt == 1:
                        logger.info("Trying to re-click the checkbox...")
                        try:
                            checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                            for cb in checkboxes:
                                parent_row = cb.find_element(By.XPATH, "./ancestor::tr")
                                if self.device_serial in parent_row.text and cb.is_displayed():
                                    if not cb.is_selected():
                                        self.driver.execute_script("arguments[0].click();", cb)
                                        logger.info("Re-clicked checkbox")
                                    else:
                                        logger.info("Checkbox is already selected")
                                    break
                        except Exception as e:
                            logger.error(f"Failed to re-click checkbox: {e}")
                    
                    # Save screenshot to see current state
                    self.save_debug_info(f"5_unclaim_search_attempt_{attempt + 1}")
                    time.sleep(3)
            
            if not unclaim_btn:
                logger.error("Could not find Unclaim button after all attempts")
                self.save_debug_info("6_no_unclaim_button_final")
                
                # Final check - see if there's any message about why unclaim is not available
                messages = self.driver.find_elements(By.CSS_SELECTOR, "[class*='message'], [class*='alert'], [class*='notice']")
                if messages:
                    logger.info("Found messages on page:")
                    for msg in messages[:5]:
                        if msg.text:
                            logger.info(f"  Message: {msg.text}")
                
                return False
            
            # Try to click the button
            try:
                unclaim_btn.click()
                logger.info("Clicked Unclaim button")
            except Exception as e:
                logger.error(f"Failed to click Unclaim button: {e}")
                # Try JavaScript click
                try:
                    self.driver.execute_script("arguments[0].click();", unclaim_btn)
                    logger.info("Clicked Unclaim button using JavaScript")
                except Exception as js_e:
                    logger.error(f"JavaScript click also failed: {js_e}")
                    return False
            
            time.sleep(2)
            self.save_debug_info("7_after_unclaim_click")
            
            # Step 6: Confirm unclaim
            logger.info("Step 6: Confirming unclaim")
            
            confirm_btn = None
            confirm_methods = [
                (By.XPATH, "//button[contains(text(), 'Unclaim from organization')]"),
                (By.XPATH, "//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[contains(text(), 'Confirm')]"),
                (By.XPATH, "//button[contains(text(), 'Yes')]"),
                (By.XPATH, "//button[contains(@class, 'confirm')]"),
                (By.XPATH, "//button[contains(@class, 'danger')]"),
                (By.XPATH, "//button[contains(@class, 'btn-danger')]"),
                # Modal/dialog buttons
                (By.XPATH, "//div[contains(@class, 'modal')]//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//div[contains(@class, 'dialog')]//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//div[contains(@class, 'modal')]//button[contains(text(), 'Confirm')]"),
                # Sometimes the confirm is in a different format
                (By.XPATH, "//button[contains(text(), 'OK')]"),
                (By.XPATH, "//button[span[contains(text(), 'Unclaim from organization')]]")
            ]
            
            for method, selector in confirm_methods:
                try:
                    confirm_btn = self.wait.until(EC.element_to_be_clickable((method, selector)))
                    logger.info(f"Found Confirm button with: {method} = {selector}")
                    break
                except TimeoutException:
                    logger.debug(f"Confirm button not found with: {method} = {selector}")
                    continue
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
                    continue
            
            if not confirm_btn:
                logger.error("Could not find Confirm button")
                self.save_debug_info("7_no_confirm_button")
                return False
            
            confirm_btn.click()
            time.sleep(5)
            self.save_debug_info("8_after_confirm")
            
            logger.info("Successfully completed unclaim process!")
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error during unclaim: {e}")
            self.save_debug_info("error")
            return False


def main():
    parser = argparse.ArgumentParser(description="Debug Meraki Device Unclaim Process")
    parser.add_argument("--username", required=True, help="Meraki Dashboard username")
    parser.add_argument("--password", required=True, help="Meraki Dashboard password")
    parser.add_argument("--org-name", required=True, help="Organization name")
    parser.add_argument("--device-serial", required=True, help="Device serial to unclaim")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    
    args = parser.parse_args()
    
    logger.info("Starting unclaim debug process")
    logger.info(f"Organization: {args.org_name}")
    logger.info(f"Device Serial: {args.device_serial}")
    if args.headless:
        logger.info("Running in HEADLESS mode")
    
    try:
        with UnclaimDebugger(args.username, args.password, args.org_name, args.device_serial, args.headless) as debugger:
            debugger.login()
            success = debugger.debug_unclaim_process()
            
            if success:
                logger.info("Debug process completed successfully!")
            else:
                logger.error("Debug process failed - check screenshots and logs")
    except Exception as e:
        logger.error(f"Debug session failed: {e}")
        raise


if __name__ == "__main__":
    main()
