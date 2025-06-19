#!/usr/bin/env python3
"""
Meraki Network Migration Tool with UI Automation
Complete migration with explicit org/network names and IDs
"""

import json
import logging
import argparse
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import requests
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
import subprocess
import psutil
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'meraki_migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set specific loggers to WARNING to reduce noise
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("selenium").setLevel(logging.WARNING)


class MerakiAPIClient:
    """Handles all Meraki API operations"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.meraki.com/api/v1"
        self.headers = {
            "X-Cisco-Meraki-API-Key": api_key,
            "Content-Type": "application/json"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _api_call(self, method: str, endpoint: str, data: Optional[Dict] = None, 
                  params: Optional[Dict] = None) -> Any:
        """Make API call with retry logic"""
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(3):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params
                )
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                # Don't retry on 404s - feature not available
                if response.status_code == 404:
                    return None
                
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                return None
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # Feature not available for this network/device
                    return None
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"API call failed: {e}")
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    
    def get_organizations(self) -> List[Dict]:
        """Get all organizations"""
        return self._api_call("GET", "/organizations")
    
    def verify_org_access(self, org_id: str, expected_name: str) -> bool:
        """Verify organization ID and name match"""
        try:
            org = self._api_call("GET", f"/organizations/{org_id}")
            if org and org['name'] == expected_name:
                logger.info(f"✓ Verified org: {expected_name} (ID: {org_id})")
                return True
            else:
                logger.error(f"✗ Org name mismatch. Expected: {expected_name}, Got: {org.get('name', 'N/A')}")
                return False
        except Exception as e:
            logger.error(f"✗ Cannot access org {org_id}: {e}")
            return False
    
    def verify_network_access(self, network_id: str, expected_name: str) -> bool:
        """Verify network ID and name match"""
        try:
            network = self._api_call("GET", f"/networks/{network_id}")
            if network and network['name'] == expected_name:
                logger.info(f"✓ Verified network: {expected_name} (ID: {network_id})")
                return True
            else:
                logger.error(f"✗ Network name mismatch. Expected: {expected_name}, Got: {network.get('name', 'N/A')}")
                return False
        except Exception as e:
            logger.error(f"✗ Cannot access network {network_id}: {e}")
            return False
    
    def get_network_info(self, network_id: str) -> Dict:
        """Get network information"""
        return self._api_call("GET", f"/networks/{network_id}")
    
    def get_devices(self, network_id: str) -> List[Dict]:
        """Get all devices in a network"""
        return self._api_call("GET", f"/networks/{network_id}/devices")
    
    def create_network(self, org_id: str, network_config: Dict) -> str:
        """Create a new network"""
        return self._api_call("POST", f"/organizations/{org_id}/networks", data=network_config)['id']
    
    def add_devices_to_network(self, network_id: str, serials: List[str]) -> bool:
        """Add devices to network"""
        try:
            self._api_call("POST", f"/networks/{network_id}/devices/claim", 
                          data={"serials": serials})
            return True
        except Exception as e:
            logger.error(f"Failed to add devices to network: {e}")
            return False


class ComprehensiveBackup:
    """Handles comprehensive backup of all network and device settings"""
    
    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client
    
    def backup_all_settings(self, org_id: str, org_name: str, network_id: str, network_name: str) -> Dict:
        """Backup all network and device settings comprehensively"""
        logger.info(f"Starting comprehensive backup for network '{network_name}'")
        
        backup = {
            "timestamp": datetime.now().isoformat(),
            "org_id": org_id,
            "org_name": org_name,
            "network_id": network_id,
            "network_name": network_name,
            "network_info": {},
            "devices": [],
            "network_settings": {
                "switch": {},
                "routing": {},
                "security": {},
                "monitoring": {}
            },
            "device_settings": {}
        }
        
        # Get network info
        backup["network_info"] = self.api.get_network_info(network_id)
        logger.info("Backed up network info")
        
        # Get devices
        devices = self.api.get_devices(network_id)
        backup["devices"] = devices
        logger.info(f"Found {len(devices)} devices")
        
        # Backup network-level switch settings
        self._backup_switch_network_settings(network_id, backup["network_settings"]["switch"])
        
        # Backup routing settings
        self._backup_routing_settings(network_id, backup["network_settings"]["routing"])
        
        # Backup security settings
        self._backup_security_settings(network_id, backup["network_settings"]["security"])
        
        # Backup monitoring settings
        self._backup_monitoring_settings(network_id, backup["network_settings"]["monitoring"])
        
        # Backup device-specific settings
        for device in devices:
            serial = device['serial']
            backup["device_settings"][serial] = self._backup_device_settings(serial, device)
        
        # Log backup summary
        logger.info("=" * 50)
        logger.info("BACKUP SUMMARY")
        logger.info("=" * 50)
        logger.info(f"Organization: {org_name} ({org_id})")
        logger.info(f"Network: {network_name} ({network_id})")
        logger.info(f"Devices: {len(devices)}")
        
        # Count backed up settings
        switch_count = sum(1 for v in backup["network_settings"]["switch"].values() if v)
        routing_count = sum(1 for v in backup["network_settings"]["routing"].values() if v)
        security_count = sum(1 for v in backup["network_settings"]["security"].values() if v)
        monitoring_count = sum(1 for v in backup["network_settings"]["monitoring"].values() if v)
        
        logger.info(f"Network Settings Backed Up:")
        logger.info(f"  - Switch settings: {switch_count}")
        logger.info(f"  - Routing settings: {routing_count}")
        logger.info(f"  - Security settings: {security_count}")
        logger.info(f"  - Monitoring settings: {monitoring_count}")
        
        port_count = sum(len(d.get("ports", [])) for d in backup["device_settings"].values())
        logger.info(f"Device Settings Backed Up:")
        logger.info(f"  - Total ports configured: {port_count}")
        logger.info("=" * 50)
        
        return backup
    
    def _backup_switch_network_settings(self, network_id: str, settings: Dict):
        """Backup switch-specific network settings"""
        endpoints = {
            "stp": f"/networks/{network_id}/switch/stp",
            "mtu": f"/networks/{network_id}/switch/mtu",
            "settings": f"/networks/{network_id}/switch/settings",
            "accessPolicies": f"/networks/{network_id}/switch/accessPolicies",
            "portSchedules": f"/networks/{network_id}/switch/portSchedules",
            "qosRules": f"/networks/{network_id}/switch/qosRules",
            "stormControl": f"/networks/{network_id}/switch/stormControl",
            "dhcpServerPolicy": f"/networks/{network_id}/switch/dhcpServerPolicy",
            "dscpToCosMappings": f"/networks/{network_id}/switch/dscp",
            "alternateManagementInterface": f"/networks/{network_id}/switch/alternateManagementInterface",
            "linkAggregations": f"/networks/{network_id}/switch/linkAggregations"
        }
        
        # Features that commonly return 404 (not available on all networks)
        optional_features = ["dscpToCosMappings", "linkAggregations", "alternateManagementInterface"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up switch {name}")
                elif name in optional_features:
                    logger.debug(f"Switch {name} not available on this network")
                else:
                    logger.info(f"Switch {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup switch {name}: {e}")
    
    def _backup_routing_settings(self, network_id: str, settings: Dict):
        """Backup routing settings"""
        endpoints = {
            "staticRoutes": f"/networks/{network_id}/appliance/staticRoutes",
            "ospf": f"/networks/{network_id}/switch/routing/ospf",
            "multicast": f"/networks/{network_id}/switch/routing/multicast",
            "warmSpare": f"/networks/{network_id}/switch/warmSpare"
        }
        
        # Features that commonly return 404
        optional_features = ["warmSpare", "ospf"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up routing {name}")
                elif name in optional_features:
                    logger.debug(f"Routing {name} not available on this network")
                else:
                    logger.info(f"Routing {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup routing {name}: {e}")
    
    def _backup_security_settings(self, network_id: str, settings: Dict):
        """Backup security settings including ACLs"""
        endpoints = {
            "accessControlLists": f"/networks/{network_id}/switch/accessControlLists",
            "portSecurity": f"/networks/{network_id}/switch/portSecurity",
            "stpGuard": f"/networks/{network_id}/switch/stpGuard"
        }
        
        # Features that commonly return 404 (newer features)
        optional_features = ["portSecurity", "stpGuard"]
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up security {name}")
                elif name in optional_features:
                    logger.debug(f"Security {name} not available on this network")
                else:
                    logger.info(f"Security {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup security {name}: {e}")
    
    def _backup_monitoring_settings(self, network_id: str, settings: Dict):
        """Backup monitoring settings"""
        endpoints = {
            "snmp": f"/networks/{network_id}/snmp",
            "syslog": f"/networks/{network_id}/syslogServers",
            "netflow": f"/networks/{network_id}/netflow",
            "alerts": f"/networks/{network_id}/alerts/settings"
        }
        
        for name, endpoint in endpoints.items():
            try:
                result = self.api._api_call("GET", endpoint)
                if result is not None:
                    settings[name] = result
                    logger.info(f"Backed up monitoring {name}")
                else:
                    logger.info(f"Monitoring {name} not configured")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup monitoring {name}: {e}")
    
    def _backup_device_settings(self, serial: str, device_info: Dict) -> Dict:
        """Backup all device-specific settings"""
        device_name = device_info.get('name', 'Unnamed')
        logger.info(f"Backing up device {serial} ({device_name})")
        
        settings = {
            "info": device_info,
            "ports": [],
            "management": {},
            "routing": {},
            "dhcp": {}
        }
        
        # Management interface (includes IP settings)
        try:
            result = self.api._api_call("GET", f"/devices/{serial}/managementInterface")
            if result is not None:
                settings["management"] = result
            else:
                logger.debug(f"No management interface configured for {serial}")
        except Exception as e:
            if "404" not in str(e):
                logger.warning(f"Could not backup management interface for {serial}: {e}")
        
        # Switch ports (all port-level settings)
        if device_info.get('model', '').startswith('MS'):
            try:
                ports = self.api._api_call("GET", f"/devices/{serial}/switch/ports")
                if ports is not None:
                    settings["ports"] = ports
                    logger.info(f"Backed up {len(ports)} ports for {serial}")
                else:
                    logger.info(f"No port configuration for {serial}")
            except Exception as e:
                if "404" not in str(e):
                    logger.warning(f"Could not backup ports for {serial}: {e}")
            
            # Routing interfaces (Layer 3) - only for L3 switches
            try:
                interfaces = self.api._api_call("GET", f"/devices/{serial}/switch/routing/interfaces")
                if interfaces is not None:
                    settings["routing"]["interfaces"] = interfaces
                    logger.debug(f"Backed up routing interfaces for {serial}")
            except Exception:
                pass  # Not all switches support L3
            
            # Static routes - only for L3 switches
            try:
                routes = self.api._api_call("GET", f"/devices/{serial}/switch/routing/staticRoutes")
                if routes is not None:
                    settings["routing"]["staticRoutes"] = routes
                    logger.debug(f"Backed up static routes for {serial}")
            except Exception:
                pass  # Not all switches support L3
            
            # DHCP settings - only for L3 switches
            try:
                dhcp = self.api._api_call("GET", f"/devices/{serial}/switch/dhcp/v4/servers")
                if dhcp is not None:
                    settings["dhcp"]["subnets"] = dhcp
                    logger.debug(f"Backed up DHCP settings for {serial}")
            except Exception:
                pass  # Not all switches support DHCP server
        
        return settings


class MerakiUIAutomation:
    """Handles UI automation for device unclaim/claim operations"""
    
    def __init__(self, username: str, password: str, headless: bool = False):
        self.username = username
        self.password = password
        self.driver = None
        self.wait = None
        self.headless = headless
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
    
    def kill_chrome_processes(self):
        """Kill any existing Chrome/ChromeDriver processes using psutil for better cross-platform support"""
        try:
            killed_count = 0
            chrome_names = ['chrome', 'chromium', 'google-chrome', 'chromedriver', 'Chrome', 'Google Chrome']
            
            # Use psutil for more reliable process killing
            try:
                import psutil
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        process_name = proc.info['name'].lower()
                        for chrome_name in chrome_names:
                            if chrome_name.lower() in process_name:
                                proc.kill()
                                killed_count += 1
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except ImportError:
                # Fallback to system commands if psutil not available
                for process in chrome_names:
                    try:
                        subprocess.run(['pkill', '-9', '-f', process], 
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    except Exception:
                        pass
            
            # Clean up Chrome temp directories
            import glob
            temp_patterns = [
                '/tmp/.com.google.Chrome.*',
                '/tmp/chrome*',
                '/tmp/meraki_chrome*',
                '/tmp/.org.chromium.*',
                os.path.join(tempfile.gettempdir(), '.com.google.Chrome.*'),
                os.path.join(tempfile.gettempdir(), 'chrome*'),
                os.path.join(tempfile.gettempdir(), 'meraki_chrome*')
            ]
            
            for pattern in temp_patterns:
                for temp_dir in glob.glob(pattern):
                    try:
                        if os.path.isdir(temp_dir):
                            shutil.rmtree(temp_dir)
                    except Exception:
                        pass
            
            if killed_count > 0:
                logger.info(f"Killed {killed_count} Chrome-related processes")
                time.sleep(3)  # Give processes time to die
            
        except Exception as e:
            logger.warning(f"Error during Chrome cleanup: {e}")
    
    def setup_driver(self):
        """Setup Chrome driver with enhanced options to prevent session conflicts"""
        # Kill any existing Chrome processes first
        self.kill_chrome_processes()
        
        # Wait a bit to ensure everything is cleaned up
        time.sleep(2)
        
        options = webdriver.ChromeOptions()
        
        # Create truly unique user data directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        random_id = str(uuid.uuid4())[:8]
        self.temp_dir = os.path.join(
            tempfile.gettempdir(), 
            f'meraki_chrome_{timestamp}_{random_id}'
        )
        
        # Ensure the directory doesn't exist
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.makedirs(self.temp_dir, mode=0o700)  # Create with restricted permissions
        
        logger.info(f"Using temp directory: {self.temp_dir}")
        
        # Core options for stability
        options.add_argument(f'--user-data-dir={self.temp_dir}')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=VizDisplayCompositor')
        options.add_argument('--disable-setuid-sandbox')
        
        # Additional isolation options
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-breakpad')
        options.add_argument('--disable-client-side-phishing-detection')
        options.add_argument('--disable-component-extensions-with-background-pages')
        options.add_argument('--disable-default-apps')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-features=TranslateUI')
        options.add_argument('--disable-hang-monitor')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-prompt-on-repost')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-sync')
        options.add_argument('--force-color-profile=srgb')
        options.add_argument('--metrics-recording-only')
        options.add_argument('--no-first-run')
        options.add_argument('--safebrowsing-disable-auto-update')
        options.add_argument('--enable-automation')
        options.add_argument('--password-store=basic')
        options.add_argument('--use-mock-keychain')
        
        # Memory optimization
        options.add_argument('--memory-pressure-off')
        options.add_argument('--max_old_space_size=4096')
        
        # Unique port for remote debugging to avoid conflicts
        debug_port = 9222 + int(time.time()) % 1000
        options.add_argument(f'--remote-debugging-port={debug_port}')
        
        # Headless mode if requested
        if self.headless:
            options.add_argument('--headless=new')
            logger.info("Running Chrome in HEADLESS mode")
        else:
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
        
        # Disable automation detection
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Preferences to disable various features
        prefs = {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "profile.managed_default_content_settings.images": 1,
        }
        options.add_experimental_option("prefs", prefs)
        
        # Try to find chromedriver
        chromedriver_paths = [
            '/usr/bin/chromedriver',
            '/usr/local/bin/chromedriver',
            '/opt/chrome/chromedriver',
            'chromedriver',
            './chromedriver',
            shutil.which('chromedriver')
        ]
        
        chromedriver_path = None
        for path in chromedriver_paths:
            if path and os.path.exists(path):
                chromedriver_path = path
                logger.info(f"Found ChromeDriver at: {chromedriver_path}")
                break
        
        # Initialize driver with retry logic
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if chromedriver_path:
                    from selenium.webdriver.chrome.service import Service
                    service = Service(chromedriver_path)
                    service.log_path = os.path.join(self.temp_dir, 'chromedriver.log')
                    self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)
                
                self.wait = WebDriverWait(self.driver, 20)
                logger.info("Chrome driver initialized successfully")
                break
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    logger.info("Cleaning up and retrying...")
                    self.kill_chrome_processes()
                    time.sleep(5)
                else:
                    logger.error("Failed to initialize Chrome driver after all attempts")
                    logger.error("Make sure Chrome and ChromeDriver are installed:")
                    logger.error("  sudo apt-get update")
                    logger.error("  sudo apt-get install -y google-chrome-stable chromium-chromedriver")
                    raise
    
    def wait_for_page_load(self, timeout=10):
        """Wait for page to finish loading"""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Page load wait timeout: {e}")
    
    def login(self):
        """Login to Meraki Dashboard"""
        logger.info("Logging into Meraki Dashboard")
        self.driver.get("https://dashboard.meraki.com")
        
        # Enter username
        username_field = None
        username_selectors = [
            (By.ID, "email"),
            (By.ID, "Email"),
            (By.NAME, "email"),
            (By.NAME, "Email"),
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.CSS_SELECTOR, "input[type='text'][name='email' i]")
        ]
        
        for selector_type, selector_value in username_selectors:
            try:
                username_field = self.wait.until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.debug(f"Found username field with {selector_type}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not username_field:
            raise Exception("Could not find username/email field")
        
        username_field.send_keys(self.username)
        username_field.send_keys(Keys.RETURN)
        
        # Wait and enter password
        time.sleep(2)
        password_field = None
        password_selectors = [
            (By.ID, "password"),
            (By.ID, "Password"),
            (By.NAME, "password"),
            (By.NAME, "Password"),
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.CSS_SELECTOR, "input[type='password'][name='password' i]"),
            (By.CSS_SELECTOR, "input[type='password'][name='Password' i]")
        ]
        
        for selector_type, selector_value in password_selectors:
            try:
                password_field = self.wait.until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                logger.debug(f"Found password field with {selector_type}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not password_field:
            self.driver.save_screenshot(f"login_error_{int(time.time())}.png")
            raise Exception("Could not find password field")
        
        password_field.send_keys(self.password)
        password_field.send_keys(Keys.RETURN)
        
        # Check for 2FA/verification code
        time.sleep(3)
        self._handle_2fa_if_needed()
        
        # Wait for dashboard to load
        dashboard_loaded = False
        dashboard_indicators = [
            (By.CLASS_NAME, "main-navigation"),
            (By.CLASS_NAME, "nav-bar"),
            (By.XPATH, "//span[text()='Organization']"),
            (By.XPATH, "//a[contains(@href, '/organization')]")
        ]
        
        for selector_type, selector_value in dashboard_indicators:
            try:
                self.wait.until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                dashboard_loaded = True
                logger.debug(f"Dashboard loaded, found element: {selector_type}='{selector_value}'")
                break
            except TimeoutException:
                continue
        
        if not dashboard_loaded:
            self.driver.save_screenshot(f"login_failed_{int(time.time())}.png")
            raise Exception("Dashboard did not load after login")
        
        logger.info("Successfully logged in")
        time.sleep(3)
    
    def _handle_2fa_if_needed(self):
        """Handle 2FA verification if required"""
        try:
            # Check for verification code input field
            verification_selectors = [
                (By.ID, "code"),
                (By.ID, "Code"),
                (By.ID, "verification-code"),
                (By.ID, "verificationCode"),
                (By.NAME, "code"),
                (By.NAME, "Code"),
                (By.NAME, "verificationCode"),
                (By.CSS_SELECTOR, "input[type='text'][placeholder*='code' i]"),
                (By.CSS_SELECTOR, "input[type='text'][placeholder*='verification' i]"),
                (By.CSS_SELECTOR, "input[type='number']"),
                (By.CSS_SELECTOR, "input[type='text']:not([type='password'])"),
                (By.XPATH, "//input[contains(@placeholder, 'code')]"),
                (By.XPATH, "//input[contains(@placeholder, 'verification')]"),
                (By.XPATH, "//input[@type='text' or @type='number']")
            ]
            
            verification_field = None
            for selector_type, selector_value in verification_selectors:
                try:
                    elements = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_all_elements_located((selector_type, selector_value))
                    )
                    for elem in elements:
                        if elem.is_displayed() and elem.get_attribute('type') != 'password':
                            elem_id = elem.get_attribute('id') or ''
                            elem_name = elem.get_attribute('name') or ''
                            if 'email' not in elem_id.lower() and 'email' not in elem_name.lower():
                                verification_field = elem
                                logger.info(f"Found verification code field with {selector_type}='{selector_value}'")
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
                
                logger.info("Enter the verification code from your email:")
                verification_code = input("Verification code: ").strip()
                
                if verification_code:
                    verification_field.clear()
                    verification_field.send_keys(verification_code)
                    
                    # Try to find and click submit button
                    submit_selectors = [
                        (By.XPATH, "//button[contains(text(), 'Verify')]"),
                        (By.XPATH, "//button[contains(text(), 'Submit')]"),
                        (By.XPATH, "//button[contains(text(), 'Continue')]"),
                        (By.XPATH, "//button[contains(text(), 'Sign in')]"),
                        (By.XPATH, "//button[contains(text(), 'Log in')]"),
                        (By.XPATH, "//input[@type='submit']"),
                        (By.CSS_SELECTOR, "button[type='submit']"),
                        (By.XPATH, "//button[not(@disabled)]")
                    ]
                    
                    button_clicked = False
                    for selector_type, selector_value in submit_selectors:
                        try:
                            buttons = self.driver.find_elements(selector_type, selector_value)
                            for btn in buttons:
                                if btn.is_displayed() and btn.is_enabled():
                                    btn.click()
                                    logger.info(f"Clicked verification submit button: {btn.text}")
                                    button_clicked = True
                                    break
                            if button_clicked:
                                break
                        except Exception:
                            continue
                    
                    if not button_clicked:
                        verification_field.send_keys(Keys.RETURN)
                        logger.info("Pressed Enter to submit verification code")
                
                logger.info("=" * 60)
                logger.info("Waiting for verification to process...")
                
                time.sleep(10)
                
            else:
                logger.info("Checking if 2FA is required...")
                time.sleep(5)
                
                if not self._is_dashboard_loaded():
                    logger.info("=" * 60)
                    logger.info("2FA may be required")
                    logger.info("If you see a verification code field in the browser:")
                    logger.info("1. Check your email for the code")
                    logger.info("2. Enter it in the browser")
                    logger.info("3. Click submit/verify")
                    logger.info("=" * 60)
                    input("Press Enter after completing 2FA (or if no 2FA is needed)...")
                
        except Exception as e:
            logger.debug(f"Error during 2FA check: {e}")
    
    def _is_dashboard_loaded(self):
        """Check if dashboard has loaded"""
        dashboard_indicators = [
            (By.CLASS_NAME, "main-navigation"),
            (By.CLASS_NAME, "nav-bar"),
            (By.XPATH, "//span[text()='Organization']"),
            (By.XPATH, "//a[contains(@href, '/organization')]")
        ]
        
        for selector_type, selector_value in dashboard_indicators:
            try:
                self.driver.find_element(selector_type, selector_value)
                return True
            except NoSuchElementException:
                continue
        return False
    
    def select_organization(self, org_name: str):
        """Select organization by name"""
        logger.info(f"Selecting organization: {org_name}")
        
        # Check if we're on the organizations overview page
        current_url = self.driver.current_url
        if "/organizations" in current_url or "global_overview" in current_url:
            # Click on organization in table
            org_link_selectors = [
                (By.LINK_TEXT, org_name),
                (By.PARTIAL_LINK_TEXT, org_name),
                (By.XPATH, f"//a[contains(text(), '{org_name}')]"),
                (By.XPATH, f"//a[contains(., '{org_name}')]"),
                (By.XPATH, f"//td[contains(text(), '{org_name}')]//a"),
                (By.XPATH, f"//tr[contains(., '{org_name}')]//a"),
            ]
            
            for method, selector in org_link_selectors:
                try:
                    org_element = self.wait.until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    org_element.click()
                    logger.info(f"Clicked on organization: {org_name}")
                    break
                except Exception:
                    continue
        else:
            # Use org selector dropdown
            try:
                org_selector = self.wait.until(
                    EC.element_to_be_clickable((By.CLASS_NAME, "org-selector"))
                )
                org_selector.click()
                
                # Find and click org
                time.sleep(1)
                org_elements = self.driver.find_elements(By.CLASS_NAME, "org-name")
                for elem in org_elements:
                    if org_name.lower() in elem.text.lower():
                        elem.click()
                        logger.info(f"Selected organization: {org_name}")
                        break
            except Exception as e:
                logger.error(f"Failed to select organization: {e}")
                raise
        
        time.sleep(3)
    
    def navigate_to_switches(self, network_name: str) -> bool:
        """Navigate to Network > Switches page"""
        logger.info(f"Navigating to switches page for network: {network_name}")
        
        # First, find and click on the network
        network_selectors = [
            (By.XPATH, f"//a[contains(text(), '{network_name}')]"),
            (By.XPATH, f"//span[contains(text(), '{network_name}')]"),
            (By.PARTIAL_LINK_TEXT, network_name)
        ]
        
        network_found = False
        for method, selector in network_selectors:
            try:
                network_element = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((method, selector))
                )
                network_element.click()
                network_found = True
                logger.info(f"Clicked on network: {network_name}")
                self.wait_for_page_load()
                time.sleep(3)
                break
            except Exception:
                continue
        
        if not network_found:
            logger.error(f"Could not find network '{network_name}'")
            return False
        
        # Try direct URL navigation to switches
        current_url = self.driver.current_url
        if "/manage/" in current_url:
            url_parts = current_url.split('/manage/')
            if len(url_parts) > 1:
                base_url = url_parts[0]
                import re
                network_id_match = re.search(r'/(N_\d+|L_\d+)', current_url)
                if network_id_match:
                    network_id = network_id_match.group(1)
                    switches_url = f"{base_url}/{network_id}/manage/nodes/switches"
                    logger.info(f"Navigating to: {switches_url}")
                    self.driver.get(switches_url)
                    self.wait_for_page_load()
                    time.sleep(3)
                    
                    if "/switches" in self.driver.current_url:
                        logger.info("Successfully navigated to switches page")
                        return True
        
        # Try menu navigation
        switch_menu_selectors = [
            (By.XPATH, "//span[text()='Switches']"),
            (By.XPATH, "//a[contains(text(), 'Switches')]"),
            (By.XPATH, "//a[contains(@href, '/switches')]"),
            (By.PARTIAL_LINK_TEXT, "Switches")
        ]
        
        for method, selector in switch_menu_selectors:
            try:
                switch_element = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((method, selector))
                )
                switch_element.click()
                logger.info("Clicked on Switches menu")
                self.wait_for_page_load()
                time.sleep(3)
                return True
            except Exception:
                continue
        
        logger.error("Could not navigate to switches page")
        return False
    
    def remove_devices_from_network(self, org_name: str, network_name: str, device_serials: List[str]) -> bool:
        """Remove devices from network before unclaiming"""
        logger.info(f"Removing {len(device_serials)} devices from network '{network_name}'")
        
        # Navigate to switches page
        if not self.navigate_to_switches(network_name):
            logger.error("Failed to navigate to switches page")
            return False
        
        # Remove each device
        for serial in device_serials:
            logger.info(f"Removing device {serial} from network")
            
            # Search for device if search box exists
            try:
                search_box = self.driver.find_element(By.CSS_SELECTOR, "input[type='search']")
                search_box.clear()
                search_box.send_keys(serial)
                search_box.send_keys(Keys.RETURN)
                time.sleep(2)
            except:
                pass
            
            # Click on device to go to details
            device_selectors = [
                (By.XPATH, f"//a[contains(text(), '{serial}')]"),
                (By.XPATH, f"//td[contains(text(), '{serial}')]"),
                (By.PARTIAL_LINK_TEXT, serial)
            ]
            
            device_found = False
            for method, selector in device_selectors:
                try:
                    device_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    device_element.click()
                    device_found = True
                    logger.info(f"Clicked on device {serial}")
                    self.wait_for_page_load()
                    time.sleep(3)
                    break
                except Exception:
                    continue
            
            if not device_found:
                logger.error(f"Could not find device {serial}")
                continue
            
            # Look for Remove from network option
            remove_selectors = [
                (By.XPATH, "//button[contains(text(), 'Remove from network')]"),
                (By.XPATH, "//a[contains(text(), 'Remove from network')]"),
                (By.XPATH, "//button[contains(text(), 'Remove')]"),
                # Check dropdowns
                (By.XPATH, "//button[contains(@class, 'dropdown')]"),
                (By.CSS_SELECTOR, "button[class*='dropdown']")
            ]
            
            remove_found = False
            for method, selector in remove_selectors:
                try:
                    element = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    
                    # If it's a dropdown, click it first
                    if 'dropdown' in element.get_attribute('class'):
                        element.click()
                        time.sleep(1)
                        
                        # Look for Remove option in dropdown
                        remove_option = self.wait.until(
                            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Remove from network')]"))
                        )
                        remove_option.click()
                        remove_found = True
                    else:
                        element.click()
                        remove_found = True
                    
                    if remove_found:
                        logger.info("Clicked Remove from network")
                        break
                except Exception:
                    continue
            
            if not remove_found:
                logger.error(f"Could not find Remove option for device {serial}")
                continue
            
            # Confirm removal
            time.sleep(2)
            confirm_selectors = [
                (By.XPATH, "//button[contains(text(), 'Remove')]"),
                (By.XPATH, "//button[contains(text(), 'Confirm')]"),
                (By.XPATH, "//button[contains(@class, 'confirm')]")
            ]
            
            for method, selector in confirm_selectors:
                try:
                    confirm_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    confirm_btn.click()
                    logger.info(f"Confirmed removal of device {serial}")
                    time.sleep(3)
                    break
                except Exception:
                    continue
            
            # Navigate back to switches list
            self.driver.back()
            self.wait_for_page_load()
            time.sleep(2)
        
        logger.info(f"Completed removing {len(device_serials)} devices from network")
        return True
    
    def unclaim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Unclaim devices from organization (after removing from network)"""
        try:
            # Navigate to Organization > Inventory
            logger.info("Navigating to Organization > Inventory")
            current_url = self.driver.current_url
            
            if "/organization/" in current_url:
                # Try direct URL navigation
                url_parts = current_url.split('/manage/')
                if len(url_parts) > 1:
                    base_url = url_parts[0]
                    inventory_url = f"{base_url}/manage/organization/inventory"
                    logger.info(f"Navigating directly to: {inventory_url}")
                    self.driver.get(inventory_url)
                    time.sleep(5)
            
            # If not on inventory page, try to find the menu
            if "/inventory" not in self.driver.current_url:
                # Try to find Organization menu or direct Inventory link
                menu_found = False
                menu_methods = [
                    # Direct inventory link
                    (By.XPATH, "//a[contains(text(), 'Inventory')]"),
                    (By.XPATH, "//a[contains(@href, '/inventory')]"),
                    (By.LINK_TEXT, "Inventory"),
                    (By.PARTIAL_LINK_TEXT, "Inventory"),
                    # Organization menu
                    (By.XPATH, "//span[text()='Organization']"),
                    (By.XPATH, "//span[contains(text(), 'Organization')]"),
                ]
                
                for method, selector in menu_methods:
                    try:
                        element = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        
                        if "Inventory" in element.text or "inventory" in (element.get_attribute('href') or ''):
                            element.click()
                            menu_found = True
                            logger.info("Clicked on Inventory link")
                            break
                        elif "Organization" in element.text:
                            element.click()
                            logger.info("Clicked on Organization menu")
                            time.sleep(2)
                            
                            inventory_link = self.wait.until(
                                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
                            )
                            inventory_link.click()
                            menu_found = True
                            logger.info("Clicked on Inventory submenu")
                            break
                    except Exception:
                        continue
                
                if not menu_found:
                    logger.error("Could not navigate to inventory page")
                    return False
            
            time.sleep(3)
            
            # Search and select devices
            for serial in device_serials:
                logger.info(f"Selecting device {serial}")
                
                # Search for device
                search_box = None
                search_methods = [
                    (By.CLASS_NAME, "search-box"),
                    (By.CSS_SELECTOR, "input[type='search']"),
                    (By.CSS_SELECTOR, "input[placeholder*='Search' i]"),
                    (By.CSS_SELECTOR, "input[placeholder*='search' i]"),
                    (By.XPATH, "//input[@type='search']"),
                    (By.XPATH, "//input[contains(@placeholder, 'Search')]")
                ]
                
                for method, selector in search_methods:
                    try:
                        search_box = self.wait.until(EC.presence_of_element_located((method, selector)))
                        break
                    except TimeoutException:
                        continue
                
                if not search_box:
                    logger.error("Could not find search box")
                    return False
                
                search_box.clear()
                search_box.send_keys(serial)
                search_box.send_keys(Keys.RETURN)
                
                # Wait for search results to load
                time.sleep(3)
                
                # Select device checkbox
                checkbox = None
                checkbox_methods = [
                    (By.XPATH, f"//tr[contains(.,'{serial}')]/td[1]//input[@type='checkbox']"),
                    (By.XPATH, f"//tr[contains(.,'{serial}')]//input[@type='checkbox']"),
                    (By.XPATH, f"//td[contains(text(),'{serial}')]/parent::tr//input[@type='checkbox']"),
                    (By.XPATH, f"//input[@type='checkbox' and ancestor::tr[contains(., '{serial}')]]"),
                ]
                
                for method, selector in checkbox_methods:
                    try:
                        checkbox = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        logger.info(f"Found checkbox with: {method}")
                        break
                    except Exception:
                        continue
                
                # If specific selectors fail, use the approach that worked
                if not checkbox:
                    logger.info("Using alternative checkbox selection method")
                    all_rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr, table tr")
                    
                    for row in all_rows:
                        if serial in row.text:
                            row_checkboxes = row.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                            if row_checkboxes:
                                try:
                                    row_checkboxes[0].click()
                                    logger.info("Clicked checkbox using alternative method")
                                    checkbox = row_checkboxes[0]
                                    break
                                except Exception as e:
                                    # Try JavaScript click
                                    try:
                                        self.driver.execute_script("arguments[0].click();", row_checkboxes[0])
                                        logger.info("Clicked checkbox using JavaScript")
                                        checkbox = row_checkboxes[0]
                                        break
                                    except:
                                        logger.error(f"Failed to click checkbox: {e}")
                
                if not checkbox:
                    logger.error(f"Could not select device {serial}")
                    return False
            
            # Wait for UI to update after checkbox selection
            time.sleep(2)
            
            # Click unclaim button
            logger.info("Looking for Unclaim button")
            unclaim_btn = None
            
            # Wait for Unclaim button to appear (might be dynamically shown)
            for attempt in range(3):
                unclaim_methods = [
                    (By.XPATH, "//button[contains(text(), 'Unclaim')]"),
                    (By.XPATH, "//button[contains(., 'Unclaim')]"),
                    (By.XPATH, "//button[contains(@class, 'unclaim')]"),
                    (By.XPATH, "//a[contains(text(), 'Unclaim')]"),
                    (By.XPATH, "//button[text()='Unclaim']"),
                    (By.XPATH, "//button[span[contains(text(), 'Unclaim')]]"),
                ]
                
                for method, selector in unclaim_methods:
                    try:
                        unclaim_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        logger.info(f"Found Unclaim button with: {method}")
                        break
                    except Exception:
                        continue
                
                if unclaim_btn:
                    break
                else:
                    logger.info(f"Unclaim button not found, attempt {attempt + 1}/3, waiting...")
                    time.sleep(3)
            
            if not unclaim_btn:
                logger.error("Could not find Unclaim button after selecting devices")
                return False
            
            unclaim_btn.click()
            logger.info("Clicked Unclaim button")
            
            # Confirm unclaim
            time.sleep(2)
            confirm_btn = None
            confirm_methods = [
                (By.XPATH, "//button[contains(text(), 'Unclaim from organization')]"),
                (By.XPATH, "//button[contains(text(), 'Unclaim')]"),
                (By.XPATH, "//button[contains(text(), 'Confirm')]"),
                (By.XPATH, "//button[contains(text(), 'Yes')]"),
                (By.XPATH, "//button[contains(@class, 'confirm')]"),
                (By.XPATH, "//button[contains(@class, 'danger')]"),
            ]
            
            for method, selector in confirm_methods:
                try:
                    confirm_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((method, selector))
                    )
                    logger.info(f"Found Confirm button with: {method}")
                    break
                except Exception:
                    continue
            
            if not confirm_btn:
                logger.error("Could not find Confirm button")
                return False
            
            confirm_btn.click()
            logger.info(f"Successfully unclaimed {len(device_serials)} devices")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unclaim devices: {e}")
            return False
    
    def claim_devices(self, org_name: str, device_serials: List[str]) -> bool:
        """Claim devices in organization"""
        try:
            # Navigate to inventory
            logger.info("Navigating to Organization > Inventory")
            current_url = self.driver.current_url
            
            if "/organization/" in current_url:
                url_parts = current_url.split('/manage/')
                if len(url_parts) > 1:
                    base_url = url_parts[0]
                    inventory_url = f"{base_url}/manage/organization/inventory"
                    logger.info(f"Navigating directly to: {inventory_url}")
                    self.driver.get(inventory_url)
                    time.sleep(5)
            
            if "/inventory" not in self.driver.current_url:
                menu_found = False
                menu_methods = [
                    (By.XPATH, "//a[contains(text(), 'Inventory')]"),
                    (By.XPATH, "//a[contains(@href, '/inventory')]"),
                    (By.LINK_TEXT, "Inventory"),
                    (By.PARTIAL_LINK_TEXT, "Inventory"),
                    (By.XPATH, "//span[text()='Organization']"),
                    (By.XPATH, "//span[contains(text(), 'Organization')]"),
                ]
                
                for method, selector in menu_methods:
                    try:
                        element = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((method, selector))
                        )
                        
                        if "Inventory" in element.text or "inventory" in (element.get_attribute('href') or ''):
                            element.click()
                            menu_found = True
                            logger.info("Clicked on Inventory link")
                            break
                        elif "Organization" in element.text:
                            element.click()
                            logger.info("Clicked on Organization menu")
                            time.sleep(2)
                            
                            inventory_link = self.wait.until(
                                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Inventory')]"))
                            )
                            inventory_link.click()
                            menu_found = True
                            logger.info("Clicked on Inventory submenu")
                            break
                    except Exception:
                        continue
                
                if not menu_found:
                    logger.error("Could not navigate to inventory page")
                    return False
            
            time.sleep(3)
            
            # Click claim button
            claim_btn = None
            claim_methods = [
                (By.XPATH, "//button[contains(text(), 'Claim')]"),
                (By.XPATH, "//button[contains(., 'Claim')]"),
                (By.XPATH, "//a[contains(text(), 'Claim')]"),
                (By.CSS_SELECTOR, "button[class*='claim']")
            ]
            
            for method, selector in claim_methods:
                try:
                    claim_btn = self.wait.until(EC.element_to_be_clickable((method, selector)))
                    break
                except TimeoutException:
                    continue
            
            if not claim_btn:
                logger.error("Could not find Claim button")
                return False
            
            claim_btn.click()
            
            # Enter serials
            logger.info(f"Claiming {len(device_serials)} devices")
            serials_field = None
            serial_field_methods = [
                (By.XPATH, "//textarea[@placeholder='Enter serials']"),
                (By.XPATH, "//textarea[contains(@placeholder, 'serial')]"),
                (By.XPATH, "//textarea[contains(@placeholder, 'Serial')]"),
                (By.CSS_SELECTOR, "textarea[placeholder*='serial' i]"),
                (By.TAG_NAME, "textarea")
            ]
            
            for method, selector in serial_field_methods:
                try:
                    serials_field = self.wait.until(EC.presence_of_element_located((method, selector)))
                    break
                except TimeoutException:
                    continue
            
            if not serials_field:
                logger.error("Could not find serials input field")
                return False
            
            serials_field.send_keys('\n'.join(device_serials))
            
            # Submit claim
            submit_btn = None
            submit_methods = [
                (By.XPATH, "//button[contains(text(), 'Claim')]"),
                (By.XPATH, "//button[contains(text(), 'Submit')]"),
                (By.XPATH, "//button[contains(text(), 'Add')]"),
                (By.CSS_SELECTOR, "button[type='submit']")
            ]
            
            for method, selector in submit_methods:
                try:
                    buttons = self.driver.find_elements(method, selector)
                    # Find the submit button (not the initial claim button)
                    for btn in buttons:
                        if btn != claim_btn and btn.is_displayed() and btn.is_enabled():
                            submit_btn = btn
                            break
                    if submit_btn:
                        break
                except Exception:
                    continue
            
            if not submit_btn:
                logger.error("Could not find submit button")
                return False
            
            submit_btn.click()
            
            # Wait for success
            time.sleep(5)
            
            logger.info(f"Successfully claimed {len(device_serials)} devices")
            return True
            
        except Exception as e:
            logger.error(f"Failed to claim devices: {e}")
            return False


class ComprehensiveRestore:
    """Handles restoration of all settings"""
    
    def __init__(self, api_client: MerakiAPIClient):
        self.api = api_client
    
    def restore_all_settings(self, backup: Dict, target_network_id: str, device_mapping: Optional[Dict] = None):
        """Restore all settings from backup"""
        logger.info(f"Starting comprehensive restore to network {target_network_id}")
        logger.info("=" * 50)
        
        # Restore network-level settings
        self._restore_network_settings(backup["network_settings"], target_network_id)
        
        # Restore device-specific settings
        if device_mapping:
            self._restore_device_settings(backup["device_settings"], device_mapping)
        else:
            logger.warning("No device mapping provided, skipping device-specific settings")
        
        logger.info("=" * 50)
        logger.info("RESTORE COMPLETE")
        logger.info("=" * 50)
        logger.info("Please verify the following in the Dashboard:")
        logger.info("  1. All network settings are properly configured")
        logger.info("  2. Device management IPs are correct")
        logger.info("  3. Port configurations match expectations")
        logger.info("  4. Any stack configurations are properly restored")
        logger.info("=" * 50)
    
    def _restore_network_settings(self, settings: Dict, network_id: str):
        """Restore network-level settings"""
        logger.info("Restoring network-level settings...")
        restored_count = 0
        
        # Restore switch settings
        switch_settings = settings.get("switch", {})
        
        # STP
        if switch_settings.get("stp"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/stp", 
                                  data=switch_settings["stp"])
                logger.info("Restored STP settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore STP: {e}")
        
        # MTU
        if switch_settings.get("mtu"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/mtu", 
                                  data=switch_settings["mtu"])
                logger.info("Restored MTU settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore MTU: {e}")
        
        # DHCP Server Policy
        if switch_settings.get("dhcpServerPolicy"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/dhcpServerPolicy", 
                                  data=switch_settings["dhcpServerPolicy"])
                logger.info("Restored DHCP server policy")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore DHCP server policy: {e}")
        
        # Storm Control
        if switch_settings.get("stormControl"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/switch/stormControl", 
                                  data=switch_settings["stormControl"])
                logger.info("Restored storm control settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore storm control: {e}")
        
        # Access Policies
        if switch_settings.get("accessPolicies"):
            try:
                for policy in switch_settings["accessPolicies"]:
                    policy_data = {k: v for k, v in policy.items() if k != "accessPolicyNumber"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/accessPolicies", 
                                      data=policy_data)
                logger.info(f"Restored {len(switch_settings['accessPolicies'])} access policies")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore access policies: {e}")
        
        # QoS Rules
        if switch_settings.get("qosRules"):
            try:
                for rule in switch_settings["qosRules"]:
                    rule_data = {k: v for k, v in rule.items() if k != "id"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/qosRules", 
                                      data=rule_data)
                logger.info(f"Restored {len(switch_settings['qosRules'])} QoS rules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore QoS rules: {e}")
        
        # Port Schedules
        if switch_settings.get("portSchedules"):
            try:
                for schedule in switch_settings["portSchedules"]:
                    schedule_data = {k: v for k, v in schedule.items() if k != "id"}
                    self.api._api_call("POST", f"/networks/{network_id}/switch/portSchedules", 
                                      data=schedule_data)
                logger.info(f"Restored {len(switch_settings['portSchedules'])} port schedules")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore port schedules: {e}")
        
        # Monitoring settings
        monitoring_settings = settings.get("monitoring", {})
        
        # SNMP
        if monitoring_settings.get("snmp"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/snmp", 
                                  data=monitoring_settings["snmp"])
                logger.info("Restored SNMP settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore SNMP: {e}")
        
        # Syslog
        if monitoring_settings.get("syslog"):
            try:
                for server in monitoring_settings["syslog"]:
                    self.api._api_call("POST", f"/networks/{network_id}/syslogServers", 
                                      data=server)
                logger.info(f"Restored {len(monitoring_settings['syslog'])} syslog servers")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore syslog servers: {e}")
        
        # Alerts
        if monitoring_settings.get("alerts"):
            try:
                self.api._api_call("PUT", f"/networks/{network_id}/alerts/settings", 
                                  data=monitoring_settings["alerts"])
                logger.info("Restored alert settings")
                restored_count += 1
            except Exception as e:
                logger.error(f"Failed to restore alerts: {e}")
        
        logger.info(f"Restored {restored_count} network-level settings")
    
    def _restore_device_settings(self, device_settings: Dict, device_mapping: Dict):
        """Restore device-specific settings"""
        logger.info(f"Restoring device-specific settings for {len(device_mapping)} devices...")
        
        for old_serial, new_serial in device_mapping.items():
            if old_serial not in device_settings:
                logger.warning(f"No settings found for device {old_serial}")
                continue
            
            settings = device_settings[old_serial]
            device_name = settings.get("info", {}).get("name", "Unnamed")
            logger.info(f"Restoring settings for device {new_serial} ({device_name})")
            
            restored_items = 0
            
            # Restore management interface
            if settings.get("management"):
                try:
                    mgmt_data = {k: v for k, v in settings["management"].items() 
                               if k not in ["ddnsHostnames", "wan1", "wan2"]}
                    self.api._api_call("PUT", f"/devices/{new_serial}/managementInterface", 
                                      data=mgmt_data)
                    logger.info(f"  ✓ Restored management interface for {new_serial}")
                    restored_items += 1
                except Exception as e:
                    logger.error(f"  ✗ Failed to restore management interface: {e}")
            
            # Restore switch ports
            if settings.get("ports"):
                successful_ports = 0
                failed_ports = 0
                
                for port in settings["ports"]:
                    port_id = port["portId"]
                    port_data = {k: v for k, v in port.items() 
                               if k not in ["portId", "warnings", "errors", "status", "speed", "duplex", 
                                          "usageInKbps", "cdp", "lldp", "clientCount", "powerUsageInWh"]}
                    
                    try:
                        self.api._api_call("PUT", f"/devices/{new_serial}/switch/ports/{port_id}", 
                                          data=port_data)
                        successful_ports += 1
                    except Exception as e:
                        failed_ports += 1
                        logger.debug(f"Failed to restore port {port_id}: {e}")
                
                if successful_ports > 0:
                    logger.info(f"  ✓ Restored {successful_ports} ports for {new_serial}")
                    restored_items += successful_ports
                if failed_ports > 0:
                    logger.warning(f"  ⚠ Failed to restore {failed_ports} ports for {new_serial}")
            
            logger.info(f"  Completed restoration for {new_serial}: {restored_items} items restored")


class AutomatedMigrationTool:
    """Main tool for automated migration with full org/network specification"""
    
    def __init__(self, source_api_key: str, target_api_key: str, username: str, password: str, headless: bool = False):
        self.source_api = MerakiAPIClient(source_api_key)
        self.target_api = MerakiAPIClient(target_api_key)
        self.username = username
        self.password = password
        self.headless = headless
        self.backup_tool = ComprehensiveBackup(self.source_api)
        self.restore_tool = ComprehensiveRestore(self.target_api)
    
    def execute_migration(self, 
                         source_org_id: str, source_org_name: str,
                         source_network_id: str, source_network_name: str,
                         target_org_id: str, target_org_name: str,
                         target_network_name: Optional[str] = None):
        """Execute complete automated migration with explicit names and IDs"""
        
        logger.info("=" * 70)
        logger.info("MERAKI NETWORK MIGRATION TOOL")
        logger.info("=" * 70)
        logger.info(f"Source Organization: {source_org_name} (ID: {source_org_id})")
        logger.info(f"Source Network: {source_network_name} (ID: {source_network_id})")
        logger.info(f"Target Organization: {target_org_name} (ID: {target_org_id})")
        logger.info(f"Target Network Name: {target_network_name or source_network_name + '_migrated'}")
        logger.info("=" * 70)
        
        # Step 1: Verify access
        logger.info("\nSTEP 1: Verifying access to source and target organizations")
        logger.info("-" * 50)
        
        if not self.source_api.verify_org_access(source_org_id, source_org_name):
            raise Exception("Cannot verify source organization access")
        
        if not self.source_api.verify_network_access(source_network_id, source_network_name):
            raise Exception("Cannot verify source network access")
        
        if not self.target_api.verify_org_access(target_org_id, target_org_name):
            raise Exception("Cannot verify target organization access")
        
        # Step 2: Comprehensive backup
        logger.info("\nSTEP 2: Backing up all network and device settings")
        logger.info("-" * 50)
        
        backup = self.backup_tool.backup_all_settings(
            source_org_id, source_org_name, 
            source_network_id, source_network_name
        )
        
        # Save backup
        backup_file = f"migration_backup_{source_network_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(backup, f, indent=2)
        logger.info(f"Backup saved to {backup_file}")
        
        # Get device serials
        device_serials = [d['serial'] for d in backup['devices']]
        if not device_serials:
            logger.error("No devices found in source network!")
            return None
        
        logger.info(f"Found {len(device_serials)} devices to migrate:")
        for device in backup['devices']:
            logger.info(f"  - {device.get('name', 'Unnamed')} ({device['model']}) - {device['serial']}")
        
        # Step 3: UI Automation - Remove from network, Unclaim, and Claim
        logger.info("\nSTEP 3: Moving devices via UI automation")
        logger.info("-" * 50)
        
        with MerakiUIAutomation(self.username, self.password, self.headless) as ui:
            ui.login()
            
            # Remove devices from network
            logger.info(f"\n3a. Removing devices from network '{source_network_name}'")
            if not ui.select_organization(source_org_name):
                raise Exception("Failed to select source organization")
            
            if not ui.remove_devices_from_network(source_org_name, source_network_name, device_serials):
                raise Exception("Failed to remove devices from network")
            
            # Wait for removal to process
            logger.info("Waiting 30 seconds for network removal to process...")
            time.sleep(30)
            
            # Unclaim from source
            logger.info(f"\n3b. Unclaiming devices from organization '{source_org_name}'")
            if not ui.unclaim_devices(source_org_name, device_serials):
                raise Exception("Failed to unclaim devices")
            
            # Wait for unclaim to process
            logger.info("Waiting 120 seconds for unclaim to process...")
            time.sleep(120)
            
            # Claim in target
            logger.info(f"\n3c. Claiming devices in organization '{target_org_name}'")
            if not ui.select_organization(target_org_name):
                raise Exception("Failed to select target organization")
            
            if not ui.claim_devices(target_org_name, device_serials):
                raise Exception("Failed to claim devices")
        
        # Wait for claim to process
        logger.info("Waiting 30 seconds for claim to process...")
        time.sleep(30)
        
        # Step 4: Create network and add devices
        logger.info("\nSTEP 4: Creating network and adding devices")
        logger.info("-" * 50)
        
        # Create network
        network_name = target_network_name or f"{source_network_name}_migrated"
        network_config = {
            "name": network_name,
            "productTypes": backup['network_info'].get('productTypes', ['switch']),
            "timeZone": backup['network_info'].get('timeZone', 'America/Los_Angeles')
        }
        
        logger.info(f"Creating network '{network_name}' in target organization...")
        target_network_id = self.target_api.create_network(target_org_id, network_config)
        logger.info(f"Created network with ID: {target_network_id}")
        
        # Add devices to network
        logger.info(f"Adding {len(device_serials)} devices to network...")
        if self.target_api.add_devices_to_network(target_network_id, device_serials):
            logger.info("✓ Devices successfully added to network")
        else:
            logger.warning("⚠ Failed to add some devices to network - they may need to be added manually")
        
        # Wait for devices to be ready
        time.sleep(10)
        
        # Step 5: Restore settings
        logger.info("\nSTEP 5: Restoring all network and device settings")
        logger.info("-" * 50)
        
        # Create device mapping (same serials in this case)
        device_mapping = {serial: serial for serial in device_serials}
        
        self.restore_tool.restore_all_settings(backup, target_network_id, device_mapping)
        
        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("MIGRATION COMPLETE!")
        logger.info("=" * 70)
        logger.info(f"Source: {source_org_name} > {source_network_name}")
        logger.info(f"Target: {target_org_name} > {network_name}")
        logger.info(f"Target Network ID: {target_network_id}")
        logger.info(f"Devices Migrated: {len(device_serials)}")
        logger.info(f"Backup File: {backup_file}")
        logger.info("=" * 70)
        logger.info("\nIMPORTANT: Please verify the following in the Dashboard:")
        logger.info("  1. All devices are online in the new network")
        logger.info("  2. Port configurations are correct")
        logger.info("  3. Management IPs are properly set")
        logger.info("  4. Any L3 routing or DHCP settings are functional")
        logger.info("  5. Monitoring and alerting is configured")
        logger.info("=" * 70)
        
        return target_network_id


def main():
    parser = argparse.ArgumentParser(
        description="Automated Meraki Migration Tool - Complete Network Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python3 migrate.py \\
    --source-api-key "YOUR_SOURCE_KEY" \\
    --target-api-key "YOUR_TARGET_KEY" \\
    --username "user@example.com" \\
    --password "password" \\
    --source-org-id "123456" \\
    --source-org-name "Source Organization" \\
    --source-network-id "N_123456789" \\
    --source-network-name "Production Network" \\
    --target-org-id "789012" \\
    --target-org-name "Target Organization" \\
    --target-network-name "Production Network Migrated"
        """
    )
    
    # API credentials
    parser.add_argument("--source-api-key", required=True, help="Source organization API key")
    parser.add_argument("--target-api-key", required=True, help="Target organization API key")
    
    # UI credentials
    parser.add_argument("--username", required=True, help="Meraki Dashboard username")
    parser.add_argument("--password", required=True, help="Meraki Dashboard password")
    
    # Source organization and network
    parser.add_argument("--source-org-id", required=True, help="Source organization ID")
    parser.add_argument("--source-org-name", required=True, help="Source organization name")
    parser.add_argument("--source-network-id", required=True, help="Source network ID")
    parser.add_argument("--source-network-name", required=True, help="Source network name")
    
    # Target organization
    parser.add_argument("--target-org-id", required=True, help="Target organization ID")
    parser.add_argument("--target-org-name", required=True, help="Target organization name")
    parser.add_argument("--target-network-name", help="Target network name (optional, defaults to source + '_migrated')")
    
    # Options
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode (for servers)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    # Mask password in logs
    logger.info(f"Starting migration with user: {args.username}")
    logger.info("Using separate API keys for source and target organizations")
    if args.headless:
        logger.info("Running in HEADLESS mode")
    
    try:
        tool = AutomatedMigrationTool(
            args.source_api_key, 
            args.target_api_key, 
            args.username, 
            args.password, 
            args.headless
        )
        
        tool.execute_migration(
            args.source_org_id,
            args.source_org_name,
            args.source_network_id,
            args.source_network_name,
            args.target_org_id,
            args.target_org_name,
            args.target_network_name
        )
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        logger.error("Please check the log file for details")
        raise


if __name__ == "__main__":
    main()
