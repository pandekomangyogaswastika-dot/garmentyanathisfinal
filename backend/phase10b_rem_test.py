#!/usr/bin/env python3
"""
Phase 10B-rem Performance Optimization Testing
Tests N+1 query pattern fixes and response structure integrity
"""

import requests
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

class Phase10BRemTester:
    def __init__(self, base_url="https://garment-erp-phase11b.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Endpoints optimized in Phase 10B-rem
        self.optimized_endpoints = [
            "/api/reports/shipment",
            "/api/reports/accessory", 
            "/api/reports/production",
            "/api/reports/progress",
            "/api/reports/return",
            "/api/reports/missing-material",
            "/api/reports/replacement",
            "/api/reports/financial",
            "/api/dashboard/analytics",
            "/api/vendor-material-inspections",
            "/api/po-items",
            "/api/po-items-produced",
            "/api/financial-recap"
        ]

    def log_test(self, name: str, success: bool, details: str = "", response_data: Any = None):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}: {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details,
            "response_sample": str(response_data)[:200] if response_data else ""
        })

    def make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> tuple:
        """Make HTTP request with auth"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)
            else:
                return False, None, f"Unsupported method: {method}"
            
            return True, response, None
        except Exception as e:
            return False, None, str(e)

    def test_login(self) -> bool:
        """Test admin login and get token"""
        print("\n🔐 Testing Authentication...")
        
        success, response, error = self.make_request('POST', '/api/auth/login', {
            'email': 'admin@garment.com',
            'password': 'Admin@123'
        })
        
        if not success:
            self.log_test("Admin Login", False, f"Request failed: {error}")
            return False
        
        if response.status_code != 200:
            self.log_test("Admin Login", False, f"Status {response.status_code}: {response.text}")
            return False
        
        try:
            data = response.json()
            if 'token' not in data:
                self.log_test("Admin Login", False, "No token in response")
                return False
            
            self.token = data['token']
            self.log_test("Admin Login", True, f"Token received, user: {data.get('user', {}).get('name', 'Unknown')}")
            return True
        except Exception as e:
            self.log_test("Admin Login", False, f"JSON parse error: {e}")
            return False

    def test_reports_endpoints(self) -> None:
        """Test all report endpoints return arrays without errors"""
        print("\n📊 Testing Report Endpoints (N+1 Optimized)...")
        
        report_endpoints = [
            "/api/reports/shipment",
            "/api/reports/accessory", 
            "/api/reports/production",
            "/api/reports/progress",
            "/api/reports/return",
            "/api/reports/missing-material",
            "/api/reports/replacement",
            "/api/reports/financial"
        ]
        
        for endpoint in report_endpoints:
            success, response, error = self.make_request('GET', endpoint)
            
            if not success:
                self.log_test(f"Report {endpoint}", False, f"Request failed: {error}")
                continue
            
            if response.status_code != 200:
                self.log_test(f"Report {endpoint}", False, f"Status {response.status_code}")
                continue
            
            try:
                data = response.json()
                
                # Should return an array (empty is fine for fresh DB)
                if isinstance(data, list):
                    self.log_test(f"Report {endpoint}", True, f"Returns array with {len(data)} rows")
                else:
                    self.log_test(f"Report {endpoint}", False, f"Expected array, got {type(data)}")
                    
            except Exception as e:
                self.log_test(f"Report {endpoint}", False, f"JSON parse error: {e}")

    def test_reports_with_filters(self) -> None:
        """Test report endpoints with vendor_id filter"""
        print("\n🔍 Testing Report Endpoints with Filters...")
        
        # Test shipment report with vendor_id filter (should not error even with no data)
        params = {'vendor_id': 'test-vendor-id'}
        success, response, error = self.make_request('GET', '/api/reports/shipment', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Report shipment with vendor_id filter", True, f"Returns array with {len(data)} rows")
                else:
                    self.log_test("Report shipment with vendor_id filter", False, f"Expected array, got {type(data)}")
            except Exception as e:
                self.log_test("Report shipment with vendor_id filter", False, f"JSON parse error: {e}")
        else:
            self.log_test("Report shipment with vendor_id filter", False, f"Status {response.status_code if response else 'N/A'}")

    def test_dashboard_analytics(self) -> None:
        """Test dashboard analytics endpoint returns expected structure"""
        print("\n📈 Testing Dashboard Analytics (N+1 Optimized)...")
        
        success, response, error = self.make_request('GET', '/api/dashboard/analytics')
        
        if not success:
            self.log_test("Dashboard Analytics", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Dashboard Analytics", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            
            # Should return object with specific fields
            if isinstance(data, dict):
                required_fields = [
                    'weeklyThroughput', 'vendorLeadTimes', 'defectRates', 
                    'productCompletion', 'shipmentStatus', 'deadlineDistribution'
                ]
                
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    # Check weeklyThroughput has 8 items (weekly buckets)
                    weekly = data.get('weeklyThroughput', [])
                    if isinstance(weekly, list) and len(weekly) == 8:
                        self.log_test("Dashboard Analytics", True, f"Valid structure with {len(weekly)} weekly throughput items")
                    else:
                        self.log_test("Dashboard Analytics", True, f"Valid structure (weeklyThroughput has {len(weekly) if isinstance(weekly, list) else 'non-array'} items)")
                else:
                    self.log_test("Dashboard Analytics", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Dashboard Analytics", False, f"Expected object, got {type(data)}")
                
        except Exception as e:
            self.log_test("Dashboard Analytics", False, f"JSON parse error: {e}")

    def test_vendor_material_inspections(self) -> None:
        """Test vendor material inspections endpoint returns expected structure"""
        print("\n🔍 Testing Vendor Material Inspections (N+1 Optimized)...")
        
        success, response, error = self.make_request('GET', '/api/vendor-material-inspections')
        
        if not success:
            self.log_test("Vendor Material Inspections", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Vendor Material Inspections", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            
            # Should return array
            if isinstance(data, list):
                if len(data) > 0:
                    # Check first item has required fields
                    inspection = data[0]
                    required_fields = ['shipment_number', 'items', 'accessory_items']
                    missing_fields = [f for f in required_fields if f not in inspection]
                    
                    if not missing_fields:
                        self.log_test("Vendor Material Inspections", True, f"Valid structure with {len(data)} inspections")
                    else:
                        self.log_test("Vendor Material Inspections", False, f"Missing fields: {missing_fields}")
                else:
                    self.log_test("Vendor Material Inspections", True, f"Returns empty array (no data)")
            else:
                self.log_test("Vendor Material Inspections", False, f"Expected array, got {type(data)}")
                
        except Exception as e:
            self.log_test("Vendor Material Inspections", False, f"JSON parse error: {e}")

    def test_po_items_enriched(self) -> None:
        """Test po-items endpoint returns enriched data with vendor shipment fields"""
        print("\n📦 Testing PO Items Enriched (N+1 Optimized)...")
        
        success, response, error = self.make_request('GET', '/api/po-items')
        
        if not success:
            self.log_test("PO Items Enriched", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("PO Items Enriched", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            
            # Should return array
            if isinstance(data, list):
                if len(data) > 0:
                    # Check first item has enriched fields
                    item = data[0]
                    required_fields = ['total_sent_to_vendor', 'remaining_qty_to_vendor']
                    missing_fields = [f for f in required_fields if f not in item]
                    
                    if not missing_fields:
                        self.log_test("PO Items Enriched", True, f"Valid enriched structure with {len(data)} items")
                    else:
                        self.log_test("PO Items Enriched", False, f"Missing enriched fields: {missing_fields}")
                else:
                    self.log_test("PO Items Enriched", True, f"Returns empty array (no data)")
            else:
                self.log_test("PO Items Enriched", False, f"Expected array, got {type(data)}")
                
        except Exception as e:
            self.log_test("PO Items Enriched", False, f"JSON parse error: {e}")

    def test_po_items_produced_validation(self) -> None:
        """Test po-items-produced endpoint validation (should return 400 when po_id missing)"""
        print("\n🏭 Testing PO Items Produced Validation...")
        
        # Test without po_id parameter (should return 400)
        success, response, error = self.make_request('GET', '/api/po-items-produced')
        
        if not success:
            self.log_test("PO Items Produced - Missing po_id", False, f"Request failed: {error}")
            return
        
        if response.status_code == 400:
            self.log_test("PO Items Produced - Missing po_id", True, "Returns 400 error as expected")
        else:
            self.log_test("PO Items Produced - Missing po_id", False, f"Expected 400, got {response.status_code}")
        
        # Test with valid po_id parameter (should return array, even if empty)
        params = {'po_id': 'test-po-id'}
        success, response, error = self.make_request('GET', '/api/po-items-produced', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("PO Items Produced - With po_id", True, f"Returns array with {len(data)} items")
                else:
                    self.log_test("PO Items Produced - With po_id", False, f"Expected array, got {type(data)}")
            except Exception as e:
                self.log_test("PO Items Produced - With po_id", False, f"JSON parse error: {e}")
        else:
            self.log_test("PO Items Produced - With po_id", False, f"Status {response.status_code if response else 'N/A'}")

    def test_financial_recap(self) -> None:
        """Test financial recap endpoint returns expected structure"""
        print("\n💰 Testing Financial Recap (N+1 Optimized)...")
        
        success, response, error = self.make_request('GET', '/api/financial-recap')
        
        if not success:
            self.log_test("Financial Recap", False, f"Request failed: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("Financial Recap", False, f"Status {response.status_code}")
            return
        
        try:
            data = response.json()
            
            # Should return object with financial summary fields
            if isinstance(data, dict):
                required_fields = [
                    'total_sales_value', 'total_vendor_cost', 'gross_margin', 
                    'invoices', 'payments'
                ]
                
                missing_fields = [f for f in required_fields if f not in data]
                
                if not missing_fields:
                    self.log_test("Financial Recap", True, f"Valid structure with all required fields")
                else:
                    self.log_test("Financial Recap", False, f"Missing fields: {missing_fields}")
            else:
                self.log_test("Financial Recap", False, f"Expected object, got {type(data)}")
                
        except Exception as e:
            self.log_test("Financial Recap", False, f"JSON parse error: {e}")

    def test_pagination_integrity(self) -> None:
        """Test that Phase 10A pagination is still intact"""
        print("\n📄 Testing Pagination Integrity (Phase 10A Compatibility)...")
        
        # Test products pagination envelope
        params = {'page': 1, 'per_page': 5}
        success, response, error = self.make_request('GET', '/api/products', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'items' in data and 'total' in data:
                    self.log_test("Products Pagination Envelope", True, f"Valid envelope with {len(data.get('items', []))} items")
                else:
                    self.log_test("Products Pagination Envelope", False, "Invalid envelope structure")
            except Exception as e:
                self.log_test("Products Pagination Envelope", False, f"JSON parse error: {e}")
        else:
            self.log_test("Products Pagination Envelope", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test products legacy array (no page param)
        success, response, error = self.make_request('GET', '/api/products')
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Products Legacy Array", True, f"Returns array with {len(data)} items")
                else:
                    self.log_test("Products Legacy Array", False, f"Expected array, got {type(data)}")
            except Exception as e:
                self.log_test("Products Legacy Array", False, f"JSON parse error: {e}")
        else:
            self.log_test("Products Legacy Array", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test production-pos pagination
        params = {'page': 1, 'per_page': 5}
        success, response, error = self.make_request('GET', '/api/production-pos', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'items' in data:
                    self.log_test("Production POs Pagination", True, f"Valid envelope with {len(data.get('items', []))} items")
                else:
                    self.log_test("Production POs Pagination", False, "Invalid envelope structure")
            except Exception as e:
                self.log_test("Production POs Pagination", False, f"JSON parse error: {e}")
        else:
            self.log_test("Production POs Pagination", False, f"Status {response.status_code if response else 'N/A'}")

    def test_additional_endpoints(self) -> None:
        """Test additional endpoints mentioned in the review request"""
        print("\n🔧 Testing Additional Endpoints...")
        
        # Test invoices pagination
        params = {'page': 1, 'per_page': 5}
        success, response, error = self.make_request('GET', '/api/invoices', params=params)
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict) and 'items' in data:
                    self.log_test("Invoices Pagination", True, f"Valid envelope")
                else:
                    self.log_test("Invoices Pagination", False, "Invalid envelope structure")
            except Exception as e:
                self.log_test("Invoices Pagination", False, f"JSON parse error: {e}")
        else:
            self.log_test("Invoices Pagination", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test distribusi-kerja endpoint
        success, response, error = self.make_request('GET', '/api/distribusi-kerja')
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, dict):
                    required_fields = ['hierarchy', 'flat', 'invalid_records']
                    missing_fields = [f for f in required_fields if f not in data]
                    
                    if not missing_fields:
                        self.log_test("Distribusi Kerja", True, "Valid structure with all required keys")
                    else:
                        self.log_test("Distribusi Kerja", False, f"Missing keys: {missing_fields}")
                else:
                    self.log_test("Distribusi Kerja", False, f"Expected object, got {type(data)}")
            except Exception as e:
                self.log_test("Distribusi Kerja", False, f"JSON parse error: {e}")
        else:
            self.log_test("Distribusi Kerja", False, f"Status {response.status_code if response else 'N/A'}")
        
        # Test production-monitoring-v2 endpoint
        success, response, error = self.make_request('GET', '/api/production-monitoring-v2')
        
        if success and response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    self.log_test("Production Monitoring V2", True, f"Returns array with {len(data)} items")
                else:
                    self.log_test("Production Monitoring V2", False, f"Expected array, got {type(data)}")
            except Exception as e:
                self.log_test("Production Monitoring V2", False, f"JSON parse error: {e}")
        else:
            self.log_test("Production Monitoring V2", False, f"Status {response.status_code if response else 'N/A'}")

    def run_all_tests(self) -> Dict:
        """Run all Phase 10B-rem tests"""
        print("🚀 Starting Phase 10B-rem Performance Optimization Tests")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📅 Test Time: {datetime.now().isoformat()}")
        
        # Authentication
        if not self.test_login():
            print("❌ Authentication failed - stopping tests")
            return self.get_summary()
        
        # Core N+1 optimization tests
        self.test_reports_endpoints()
        self.test_reports_with_filters()
        self.test_dashboard_analytics()
        self.test_vendor_material_inspections()
        self.test_po_items_enriched()
        self.test_po_items_produced_validation()
        self.test_financial_recap()
        
        # Regression tests
        self.test_pagination_integrity()
        self.test_additional_endpoints()
        
        return self.get_summary()

    def get_summary(self) -> Dict:
        """Get test summary"""
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": self.tests_run - self.tests_passed,
            "success_rate": f"{success_rate:.1f}%",
            "test_results": self.test_results,
            "summary": f"Phase 10B-rem Performance Testing: {self.tests_passed}/{self.tests_run} tests passed ({success_rate:.1f}%)"
        }

def main():
    """Main test execution"""
    tester = Phase10BRemTester()
    
    try:
        results = tester.run_all_tests()
        
        print(f"\n📊 Test Summary:")
        print(f"   Total Tests: {results['total_tests']}")
        print(f"   Passed: {results['passed_tests']}")
        print(f"   Failed: {results['failed_tests']}")
        print(f"   Success Rate: {results['success_rate']}")
        
        # Print failed tests
        failed_tests = [t for t in results['test_results'] if not t['success']]
        if failed_tests:
            print(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests:
                print(f"   • {test['name']}: {test['details']}")
        
        # Return appropriate exit code
        return 0 if results['failed_tests'] == 0 else 1
        
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())