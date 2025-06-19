#!/usr/bin/env python3
"""
Debug script with improved network selection
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


def debug_network_selection(driver, wait, network_name):
    """Debug function to understand network selection"""
    logger.info(f"Debugging network selection for: {network_name}")
    
    # Take screenshot before attempting selection
    driver.save_screenshot("before_network_selection.png")
    
    # Method 1: Look for network selector in header
    logger.info("Method 1: Looking for network selector in header...")
    try:
        # Find all select buttons in header
        header_buttons = driver.find_elements(By.CSS_SELECTOR, ".mds-global-nav-select-button, button[class*='select']")
        logger.info(f"Found {len(header_buttons)} header buttons")
        
        for i, btn in enumerate(header_buttons):
            btn_text = btn.text
            logger.info(f"Header button {i}: '{btn_text}'")
            
            # Check if this might be the network selector
            if i == 1 or 'network' in btn_text.lower() or network_name in btn_text:
                logger.info(f"Clicking on button: '{btn_text}'")
                btn.click()
                time.sleep(2)
                
                # Look for network in dropdown
                try:
                    network_element = wait.until(
                        EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{network_name}')]"))
                    )
                    logger.info(f"Found network element: {network_element.text}")
                    network_element.click()
                    logger.info("Successfully selected network")
                    return True
                except:
                    logger.info("Network not found in this dropdown")
                    # Close dropdown by clicking elsewhere
                    driver.find_element(By.TAG_NAME, "body").click()
                    time.sleep(1)
    except Exception as e:
        logger.error(f"Method 1 failed: {e}")
    
    # Method 2: Look for network name already displayed
    logger.info("Method 2: Checking if network is already selected...")
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if network_name in page_text:
            logger.info(f"Network '{network_name}' appears to be already selected or visible on page")
            # Try to navigate directly to switches
            return True
    except:
        pass
    
    # Method 3: Try network dropdown by class
    logger.info("Method 3: Looking for network dropdown by various selectors...")
    selectors = [
        "div[class*='network'] button",
        "button[aria-label*='network']",
        "[class*='dropdown'] button",
        "button:contains('Network')",
        ".network-selector",
        "[data-test*='network']"
    ]
    
    for selector in selectors:
        try:
            logger.info(f"Trying selector: {selector}")
            if ':contains' in selector:
                # Use JavaScript for contains selector
                elements = driver.execute_script(
                    f"return Array.from(document.querySelectorAll('button')).filter(el => el.textContent.includes('Network'))"
                )
                if elements:
                    elements[0].click()
            else:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                element.click()
            
            time.sleep(2)
            
            # Try to find network
            try:
                network_element = driver.find_element(By.XPATH, f"//*[contains(text(), '{network_name}')]")
                network_element.click()
                logger.info("Successfully selected network")
                return True
            except:
                # Close dropdown
                driver.find_element(By.TAG_NAME, "body").click()
                time.sleep(1)
        except:
            continue
    
    # Method 4: Direct navigation approach
    logger.info("Method 4: Attempting direct navigation to switches...")
    current_url = driver.current_url
    logger.info(f"Current URL: {current_url}")
    
    # Since we can't select the network, let's try to navigate directly
    # This assumes we're already in the right network context
    return False


def select_network_improved(driver, wait, network_name):
    """Improved network selection with multiple approaches"""
    logger.info(f"Attempting to select network: {network_name}")
    
    # First, debug what's on the page
    if debug_network_selection(driver, wait, network_name):
        return True
    
    # If debug didn't work, try alternative approach
    logger.info("Alternative approach: Checking if we can proceed without explicit network selection")
    
    # Take a screenshot to see current state
    driver.save_screenshot("network_selection_failed.png")
    
    # Check if we're already in a network context
    current_url = driver.current_url
    if "/n/" in current_url:
        logger.info("Already in a network context based on URL")
        return True
    
    # Try to proceed anyway - sometimes the network is already selected
    return True  # Proceed optimistically


class UnclaimDebugger:
    """Debug the unclaim process with improved network handling"""
    
    def __init__(self, username: str, password: str, org_name: str, device_serial: str, network_name: str = None, headless: bool = False):
        self.username = username
        self.password = password
        self.org_name = org_name
        self.device_serial = device_serial
        self.network_name = network_name
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
        """Save screenshot for debugging"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = f"unclaim_debug_{step}_{timestamp}.png"
        self.driver.save_screenshot(screenshot_file)
        logger.info(f"Screenshot saved: {screenshot_file}")
    
    def login(self):
        """Login to Meraki Dashboard with 2FA support"""
        logger.info("Logging into Meraki Dashboard")
        self.driver.get("https://dashboard.meraki.com")
        time.sleep(3)
        
        # Enter email
        email_field = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email'], input#email, input#Email"))
        )
        email_field.send_keys(self.username)
        email_field.send_keys(Keys.RETURN)
        time.sleep(3)
        
        # Enter password
        password_field = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password'], input#password, input#Password"))
        )
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)
        
        # Handle 2FA if needed
        time.sleep(5)
        self._handle_2fa_if_needed()
        
        # Wait for dashboard to load
        try:
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".main-navigation, .nav-bar, [href*='/organization']"))
            )
            logger.info("Successfully logged in")
        except TimeoutException:
            self.save_debug_info("login_failed")
            raise Exception("Dashboard did not load after login")
        
        time.sleep(3)
    
    def _handle_2fa_if_needed(self):
        """Handle 2FA verification if required"""
        try:
            # Look for verification code field
            verification_field = None
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text']:not([type='password']), input[type='number']")
                for elem in elements:
                    if elem.is_displayed():
                        elem_id = (elem.get_attribute('id') or '').lower()
                        elem_name = (elem.get_attribute('name') or '').lower()
                        elem_placeholder = (elem.get_attribute('placeholder') or '').lower()
                        if ('code' in elem_id or 'code' in elem_name or 'code' in elem_placeholder or
                            'verification' in elem_id or 'verification' in elem_name or 'verification' in elem_placeholder):
                            verification_field = elem
                            break
            except:
                pass
            
            if verification_field:
                logger.info("=" * 60)
                logger.info("2FA VERIFICATION REQUIRED")
                logger.info("=" * 60)
                logger.info("Please check your email for the verification code.")
                
                verification_code = input("Enter verification code: ").strip()
                
                if verification_code:
                    verification_field.clear()
                    verification_field.send_keys(verification_code)
                    
                    # Try to find and click submit button
                    try:
                        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:not([disabled])")
                        submit_btn.click()
                    except:
                        verification_field.send_keys(Keys.RETURN)
                    
                    logger.info("Submitted verification code")
                    time.sleep(10)
        except Exception as e:
            logger.debug(f"2FA check completed: {e}")
    
    def select_organization(self, org_name: str):
        """Select organization"""
        logger.info(f"Selecting organization: {org_name}")
        
        current_url = self.driver.current_url
        
        # If on organizations overview page
        if "/organizations" in current_url or "global_overview" in current_url:
            try:
                org_link = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{org_name}') or contains(., '{org_name}')]"))
                )
                org_link.click()
                logger.info(f"Clicked on organization: {org_name}")
                time.sleep(5)
                return True
            except:
                logger.error(f"Could not find organization '{org_name}'")
                return False
        else:
            # Use org selector dropdown
            try:
                org_selector = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, ".org-selector, [class*='org-selector']"))
                )
                org_selector.click()
                time.sleep(2)
                
                org_element = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{org_name}')]"))
                )
                org_element.click()
                logger.info(f"Selected organization: {org_name}")
                time.sleep(3)
                return True
            except:
                logger.error(f"Could not select organization '{org_name}'")
                return False
    
    def navigate_to_switches(self):
        """Navigate to Switching > Switches"""
        logger.info("Navigating to Switching > Switches")
        
        # Take screenshot before navigation
        self.save_debug_info("before_switches_navigation")
        
        try:
            # Method 1: Try to find Switching menu
            try:
                switching_menu = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Switching')]"))
                )
                switching_menu.click()
                time.sleep(2)
                
                # Click on Switches submenu
                switches_link = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Switches')]"))
                )
                switches_link.click()
                time.sleep(3)
                
                logger.info("Successfully navigated to Switches page via menu")
                return True
            except Exception as e:
                logger.warning(f"Menu navigation failed: {e}")
            
            # Method 2: Try direct URL navigation
            current_url = self.driver.current_url
            logger.info(f"Attempting direct URL navigation from: {current_url}")
            
            if "/n/" in current_url:
                # Extract network portion and build switches URL
                parts = current_url.split('/')
                network_index = parts.index('n') + 1
                if network_index < len(parts):
                    network_id = parts[network_index]
                    base_url = '/'.join(parts[:network_index+1])
                    # Correct URL for switches page
                    switches_url = f"{base_url}/manage/switches/"
                    logger.info(f"Navigating to: {switches_url}")
                    self.driver.get(switches_url)
                    time.sleep(5)
                    
                    # Verify we're on switches page
                    if "manage/switches" in self.driver.current_url:
                        logger.info("Successfully navigated to Switches page via URL")
                        return True
            
            # Method 3: Build URL from base
            try:
                # Get base URL
                base_url = current_url.split('/manage/')[0]
                switches_url = f"{base_url}/manage/switches/?from=switching+switches"
                logger.info(f"Method 3: Navigating to: {switches_url}")
                self.driver.get(switches_url)
                time.sleep(5)
                
                if "manage/switches" in self.driver.current_url:
                    logger.info("Successfully navigated to Switches page via constructed URL")
                    return True
            except Exception as e:
                logger.warning(f"Method 3 failed: {e}")
            
            # Method 4: Look for any switches-related link
            logger.info("Method 4: Looking for switches-related links...")
            switches_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'switches')]")
            for link in switches_links:
                if link.is_displayed():
                    href = link.get_attribute('href')
                    logger.info(f"Found switches link: {href}")
                    if 'manage/switches' in href:
                        link.click()
                        time.sleep(3)
                        return True
            
        except Exception as e:
            logger.error(f"All navigation methods failed: {e}")
            self.save_debug_info("switches_navigation_failed")
        
        return False
    
    def remove_device_from_network_switches(self):
        """Remove device from network via Switches page"""
        logger.info(f"Removing device {self.device_serial} from network switches")
        
        # Wait for page to load
        time.sleep(3)
        
        # Take screenshot to see current state
        self.save_debug_info("switches_page")
        
        # Close any open menus by clicking on the main content area
        try:
            # Click on the main content area to close any hovering menus
            main_content = self.driver.find_element(By.CSS_SELECTOR, "main, .main-content, #main-content, [role='main']")
            self.driver.execute_script("arguments[0].click();", main_content)
            time.sleep(1)
        except:
            # Alternative: click on the page title or header
            try:
                page_title = self.driver.find_element(By.CSS_SELECTOR, "h1, .page-title, .switches-title")
                page_title.click()
                time.sleep(1)
            except:
                pass
        
        # Search for device if search box exists
        try:
            search_box = self.driver.find_element(By.CSS_SELECTOR, "input[type='search'], input[placeholder*='Search']")
            search_box.clear()
            search_box.send_keys(self.device_serial)
            search_box.send_keys(Keys.RETURN)
            time.sleep(3)
            logger.info(f"Searched for device {self.device_serial}")
        except:
            logger.info("No search box found, looking for device in list")
        
        # Find device row by serial number
        device_found = False
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, tr")
        
        for row in rows:
            if self.device_serial in row.text:
                logger.info(f"Found device row containing serial {self.device_serial}")
                
                # Scroll the row into view to ensure it's not hidden
                self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", row)
                time.sleep(1)
                
                # Try multiple methods to find and click the checkbox
                checkbox_clicked = False
                
                # Method 1: Look for checkbox in the first cell
                try:
                    first_cell = row.find_element(By.CSS_SELECTOR, "td:first-child")
                    checkbox = first_cell.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                    
                    # Use JavaScript to click if the element might be obscured
                    self.driver.execute_script("arguments[0].click();", checkbox)
                    checkbox_clicked = True
                    logger.info("Selected device checkbox using JavaScript click")
                except Exception as e:
                    logger.debug(f"Method 1 failed: {e}")
                
                # Method 2: Find any checkbox in the row
                if not checkbox_clicked:
                    try:
                        checkbox = row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                        self.driver.execute_script("arguments[0].click();", checkbox)
                        checkbox_clicked = True
                        logger.info("Selected device checkbox in row")
                    except Exception as e:
                        logger.debug(f"Method 2 failed: {e}")
                
                # Method 3: Click on the row itself if it's selectable
                if not checkbox_clicked:
                    try:
                        # Some tables select the row when clicking anywhere on it
                        self.driver.execute_script("arguments[0].click();", row)
                        time.sleep(1)
                        
                        # Check if a checkbox appeared or got selected
                        try:
                            checkbox = row.find_element(By.CSS_SELECTOR, "input[type='checkbox']:checked")
                            checkbox_clicked = True
                            logger.info("Row click selected the device")
                        except:
                            pass
                    except Exception as e:
                        logger.debug(f"Method 3 failed: {e}")
                
                if checkbox_clicked:
                    device_found = True
                    time.sleep(2)
                    break
                else:
                    logger.error("Could not select device checkbox")
                    
                    # Take a screenshot to debug
                    self.save_debug_info("checkbox_selection_failed")
                    
                    # Try to identify what's blocking the checkbox
                    try:
                        # Check if there's an overlay or menu covering the checkbox
                        overlays = self.driver.find_elements(By.CSS_SELECTOR, "[class*='overlay'], [class*='menu'], [class*='dropdown']")
                        for overlay in overlays:
                            if overlay.is_displayed():
                                logger.info(f"Found potential overlay: {overlay.get_attribute('class')}")
                    except:
                        pass
        
        if not device_found:
            logger.warning(f"Device {self.device_serial} not found in Switches - might already be removed")
            return True  # Continue anyway
        
        # Look for Remove button
        remove_button = None
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled():
                btn_text = btn.text.lower()
                if 'remove' in btn_text:
                    remove_button = btn
                    logger.info(f"Found Remove button: '{btn.text}'")
                    break
        
        if not remove_button:
            logger.info("No Remove button found - device might already be removed from network")
            return True
        
        # Click Remove button
        remove_button.click()
        time.sleep(2)
        
        # Confirm removal
        try:
            # Wait for the confirmation dialog to appear
            time.sleep(1)
            
            # Look for the Remove button in the confirmation dialog
            # The dialog has a blue "Remove" button (not "Confirm" or "Yes")
            confirm_methods = [
                # Primary: Look for Remove button in a modal/dialog
                (By.XPATH, "//div[contains(@class, 'modal') or contains(@class, 'dialog')]//button[contains(text(), 'Remove')]"),
                # Secondary: Any blue/primary Remove button
                (By.XPATH, "//button[contains(@class, 'primary') or contains(@class, 'blue')][contains(text(), 'Remove')]"),
                # Tertiary: Just the Remove button text (but not the first one we clicked)
                (By.XPATH, "(//button[contains(text(), 'Remove')])[last()]"),
                # Look for Remove button that's not disabled
                (By.XPATH, "//button[contains(text(), 'Remove') and not(@disabled)]"),
                # Try the specific modal button
                (By.CSS_SELECTOR, ".modal button.primary, .dialog button.primary, button[class*='primary'][class*='button']"),
            ]
            
            confirm_btn = None
            for method, selector in confirm_methods:
                try:
                    elements = self.driver.find_elements(method, selector)
                    # Find the Remove button that's in the dialog (not the one we already clicked)
                    for elem in elements:
                        if elem.is_displayed() and elem.is_enabled():
                            # Check if this is in a modal/dialog context
                            parent_html = elem.get_attribute('outerHTML')
                            logger.debug(f"Found potential confirm button: {elem.text}")
                            if elem != remove_button:  # Make sure it's not the same button
                                confirm_btn = elem
                                logger.info(f"Found confirmation button: '{elem.text}'")
                                break
                    if confirm_btn:
                        break
                except Exception as e:
                    logger.debug(f"Method failed: {e}")
            
            if not confirm_btn:
                # Last resort: find all visible Remove buttons and click the last one
                all_remove_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Remove')]")
                for btn in reversed(all_remove_buttons):
                    if btn.is_displayed() and btn.is_enabled():
                        confirm_btn = btn
                        logger.info(f"Using last Remove button as confirmation")
                        break
            
            if confirm_btn:
                confirm_btn.click()
                logger.info("Clicked confirmation Remove button")
                time.sleep(5)
                return True
            else:
                logger.error("Could not find confirmation Remove button")
                self.save_debug_info("no_confirm_button")
                return False
                
        except Exception as e:
            logger.error(f"Could not confirm device removal: {e}")
            self.save_debug_info("removal_confirmation_failed")
            return False
    
    def navigate_to_inventory(self):
        """Navigate to Organization > Inventory"""
        logger.info("Navigating to Organization > Inventory")
        
        current_url = self.driver.current_url
        
        # Try direct navigation first
        if "/organization/" in current_url:
            try:
                base_url = current_url.split('/manage/')[0]
                inventory_url = f"{base_url}/manage/organization/inventory"
                self.driver.get(inventory_url)
                time.sleep(5)
                
                if "/inventory" in self.driver.current_url:
                    logger.info("Successfully navigated to inventory page")
                    return True
            except:
                pass
        
        # Try menu navigation
        try:
            # Look for direct inventory link first
            inventory_link = self.driver.find_element(By.XPATH, "//a[contains(text(), 'Inventory') or contains(@href, '/inventory')]")
            inventory_link.click()
            time.sleep(3)
            return True
        except:
            # Try Organization menu
            try:
                org_menu = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Organization')]"))
                )
                org_menu.click()
                time.sleep(2)
                
                inventory_link = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
                )
                inventory_link.click()
                time.sleep(3)
                return True
            except:
                logger.error("Could not navigate to inventory page")
                return False
    
    def unclaim_device(self):
        """Unclaim device from organization"""
        logger.info(f"Unclaiming device {self.device_serial} from organization")
        
        # Search for device
        search_box = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='search']"))
        )
        search_box.clear()
        search_box.send_keys(self.device_serial)
        search_box.send_keys(Keys.RETURN)
        time.sleep(3)
        
        # Find and select device
        device_row = None
        rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        for row in rows:
            if self.device_serial in row.text:
                device_row = row
                break
        
        if not device_row:
            logger.error(f"Could not find device {self.device_serial}")
            return False
        
        # Select checkbox
        checkbox = device_row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        if not checkbox.is_selected():
            checkbox.click()
            time.sleep(2)
        
        # Find and click Unclaim button
        unclaim_btn = None
        buttons = self.driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            if btn.is_displayed() and btn.is_enabled() and 'unclaim' in btn.text.lower():
                unclaim_btn = btn
                logger.info(f"Found unclaim button: {btn.text}")
                break
        
        if not unclaim_btn:
            logger.error("Could not find enabled Unclaim button")
            self.save_debug_info("no_unclaim_button")
            return False
        
        unclaim_btn.click()
        time.sleep(2)
        
        # Confirm unclaim
        try:
            confirm_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, 
                    "//button[contains(text(), 'Unclaim') or contains(text(), 'Confirm') or contains(text(), 'Yes')]"))
            )
            confirm_btn.click()
            logger.info("Confirmed device unclaim")
            time.sleep(5)
            return True
        except:
            logger.error("Could not confirm unclaim")
            return False
    
    def debug_unclaim_process(self):
        """Execute the complete unclaim process"""
        try:
            # Step 1: Select organization
            logger.info("=" * 60)
            logger.info("STEP 1: Selecting organization")
            logger.info("=" * 60)
            
            if not self.select_organization(self.org_name):
                return False
            
            # Step 2: Handle network selection (if provided)
            if self.network_name:
                logger.info("=" * 60)
                logger.info("STEP 2: Handling network context")
                logger.info("=" * 60)
                
                # Use improved network selection
                select_network_improved(self.driver, self.wait, self.network_name)
                
                # Step 3: Navigate to Switches and remove device
                logger.info("=" * 60)
                logger.info("STEP 3: Removing device from network switches")
                logger.info("=" * 60)
                
                if self.navigate_to_switches():
                    if not self.remove_device_from_network_switches():
                        logger.warning("Failed to remove device from switches, but continuing...")
                else:
                    logger.warning("Could not navigate to switches page, proceeding to inventory")
            else:
                logger.info("No network specified, skipping network removal")
            
            # Step 4: Navigate to inventory
            logger.info("=" * 60)
            logger.info("STEP 4: Navigating to inventory")
            logger.info("=" * 60)
            
            if not self.navigate_to_inventory():
                return False
            
            # Step 5: Unclaim device from organization
            logger.info("=" * 60)
            logger.info("STEP 5: Unclaiming device from organization")
            logger.info("=" * 60)
            
            if not self.unclaim_device():
                return False
            
            logger.info("=" * 60)
            logger.info("UNCLAIM PROCESS COMPLETED SUCCESSFULLY!")
            logger.info("=" * 60)
            return True
            
        except Exception as e:
            logger.error(f"Unexpected error during unclaim process: {e}")
            self.save_debug_info("error")
            return False


def main():
    parser = argparse.ArgumentParser(description="Debug Meraki Device Unclaim Process")
    parser.add_argument("--username", required=True, help="Meraki Dashboard username")
    parser.add_argument("--password", required=True, help="Meraki Dashboard password")
    parser.add_argument("--org-name", required=True, help="Organization name")
    parser.add_argument("--device-serial", required=True, help="Device serial to unclaim")
    parser.add_argument("--network-name", help="Network name (required if device is in a network)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    
    args = parser.parse_args()
    
    logger.info("Starting unclaim debug process")
    logger.info(f"Organization: {args.org_name}")
    logger.info(f"Device Serial: {args.device_serial}")
    if args.network_name:
        logger.info(f"Network: {args.network_name}")
    
    try:
        with UnclaimDebugger(
            args.username, 
            args.password, 
            args.org_name, 
            args.device_serial,
            args.network_name,
            args.headless
        ) as debugger:
            debugger.login()
            success = debugger.debug_unclaim_process()
            
            if success:
                logger.info("Debug process completed successfully!")
            else:
                logger.error("Debug process failed")
                
    except Exception as e:
        logger.error(f"Debug session failed: {e}")
        raise


if __name__ == "__main__":
    main()
