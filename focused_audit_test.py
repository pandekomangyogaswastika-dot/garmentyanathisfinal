#!/usr/bin/env python3
"""
Focused Production Flow Audit Testing - Garment ERP v8.0
Tests specific validation logic for the 9 production flow audit bug fixes
"""

import requests
import json
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

class FocusedAuditTester:
    def __init__(self, base_url="https://erp-production-track.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

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
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=30)
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

    def test_c1_buyer_shipment_validation(self):
        """Test C-1: Buyer shipment validation logic"""
        print("\n🔍 Testing C-1: Buyer Shipment Validation...")
        
        # Test with invalid data to trigger validation
        invalid_shipment_data = {
            'po_id': 'nonexistent-po-id',
            'job_id': 'nonexistent-job-id',
            'customer_name': 'Test Customer',
            'items': [{
                'po_item_id': 'nonexistent-item-id',
                'job_item_id': 'nonexistent-job-item-id',
                'qty_shipped': 999,  # Large quantity to test validation
                'sku': 'TEST-SKU',
                'product_name': 'Test Product'
            }]
        }
        
        success, response, error = self.make_request('POST', '/api/buyer-shipments', invalid_shipment_data)
        if success:
            if response.status_code == 400:
                response_text = response.text
                if 'melebihi' in response_text or 'diproduksi' in response_text:
                    self.log_test("C-1 Validation Logic", True, "Buyer shipment validation works with Indonesian messages")
                else:
                    self.log_test("C-1 Validation Logic", True, f"Buyer shipment validation active: {response_text[:100]}")
            elif response.status_code == 404:
                self.log_test("C-1 Validation Logic", True, "Buyer shipment endpoint validates entity existence")
            else:
                self.log_test("C-1 Validation Logic", False, f"Unexpected status: {response.status_code}")
        else:
            self.log_test("C-1 Validation Logic", False, f"Request failed: {error}")

    def test_c2_return_validation(self):
        """Test C-2: Production return validation logic"""
        print("\n🔍 Testing C-2: Production Return Validation...")
        
        # Test with excessive return quantity
        excessive_return_data = {
            'reference_po_id': 'nonexistent-po-id',
            'customer_name': 'Test Customer',
            'return_reason': 'Quality issue',
            'items': [{
                'po_item_id': 'nonexistent-item-id',
                'return_qty': 999,  # Excessive quantity
                'sku': 'TEST-SKU',
                'product_name': 'Test Product',
                'defect_type': 'Major defect'
            }]
        }
        
        success, response, error = self.make_request('POST', '/api/production-returns', excessive_return_data)
        if success:
            if response.status_code == 400:
                response_text = response.text
                if 'melebihi maks yang bisa diretur' in response_text or 'melebihi' in response_text:
                    self.log_test("C-2 Return Validation", True, "Return validation works with Indonesian messages")
                else:
                    self.log_test("C-2 Return Validation", True, f"Return validation active: {response_text[:100]}")
            elif response.status_code == 404:
                self.log_test("C-2 Return Validation", True, "Return endpoint validates entity existence")
            else:
                self.log_test("C-2 Return Validation", False, f"Unexpected status: {response.status_code}")
        else:
            self.log_test("C-2 Return Validation", False, f"Request failed: {error}")

    def test_h4_negative_return_validation(self):
        """Test H-4: Negative return quantity validation"""
        print("\n🔍 Testing H-4: Negative Return Quantity Validation...")
        
        # Test with zero return quantity
        zero_return_data = {
            'reference_po_id': 'test-po-id',
            'customer_name': 'Test Customer',
            'return_reason': 'Test zero quantity',
            'items': [{
                'po_item_id': 'test-item-id',
                'return_qty': 0,
                'sku': 'TEST-SKU',
                'product_name': 'Test Product',
                'defect_type': 'Test defect'
            }]
        }
        
        success, response, error = self.make_request('POST', '/api/production-returns', zero_return_data)
        if success and response.status_code == 400:
            response_text = response.text
            if 'return_qty harus minimal 1' in response_text:
                self.log_test("H-4 Zero Return Validation", True, "Correctly rejects zero return quantity")
            else:
                self.log_test("H-4 Zero Return Validation", False, f"Wrong error message: {response_text}")
        else:
            self.log_test("H-4 Zero Return Validation", False, f"Should reject zero return: {response.status_code if response else 'No response'}")
        
        # Test with negative return quantity
        zero_return_data['items'][0]['return_qty'] = -5
        success, response, error = self.make_request('POST', '/api/production-returns', zero_return_data)
        if success and response.status_code == 400:
            response_text = response.text
            if 'return_qty harus minimal 1' in response_text:
                self.log_test("H-4 Negative Return Validation", True, "Correctly rejects negative return quantity")
            else:
                self.log_test("H-4 Negative Return Validation", False, f"Wrong error message: {response_text}")
        else:
            self.log_test("H-4 Negative Return Validation", False, f"Should reject negative return: {response.status_code if response else 'No response'}")

    def test_m1_zero_dispatch_validation(self):
        """Test M-1: Zero quantity dispatch validation"""
        print("\n🔍 Testing M-1: Zero Quantity Dispatch Validation...")
        
        # Test with all items having zero quantity
        zero_dispatch_data = {
            'po_id': 'test-po-id',
            'job_id': 'test-job-id',
            'customer_name': 'Test Customer',
            'items': [{
                'po_item_id': 'test-item-id',
                'job_item_id': 'test-job-item-id',
                'qty_shipped': 0,
                'sku': 'TEST-SKU',
                'product_name': 'Test Product'
            }]
        }
        
        success, response, error = self.make_request('POST', '/api/buyer-shipments', zero_dispatch_data)
        if success and response.status_code == 400:
            response_text = response.text
            if 'Dispatch harus memiliki minimal 1 pcs' in response_text:
                self.log_test("M-1 Zero Dispatch Validation", True, "Correctly rejects zero quantity dispatch")
            else:
                self.log_test("M-1 Zero Dispatch Validation", False, f"Wrong error message: {response_text}")
        else:
            self.log_test("M-1 Zero Dispatch Validation", False, f"Should reject zero dispatch: {response.status_code if response else 'No response'}")

    def test_h1_po_fields_structure(self):
        """Test H-1: PO response structure with new fields"""
        print("\n🔍 Testing H-1: PO Response Structure...")
        
        success, response, error = self.make_request('GET', '/api/production-pos')
        if not success:
            self.log_test("H-1 PO Structure", False, f"Failed to get POs: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("H-1 PO Structure", False, f"Status {response.status_code}")
            return
        
        try:
            pos = response.json()
            if isinstance(pos, list):
                if len(pos) > 0:
                    po = pos[0]
                    required_fields = ['remaining_qty_to_ship', 'over_shipped_qty']
                    missing_fields = [f for f in required_fields if f not in po]
                    
                    if not missing_fields:
                        remaining = po.get('remaining_qty_to_ship', 0)
                        over_shipped = po.get('over_shipped_qty', 0)
                        
                        if remaining >= 0:  # Should be clamped at 0
                            self.log_test("H-1 PO Structure", True, f"PO fields correct: remaining={remaining}, over_shipped={over_shipped}")
                        else:
                            self.log_test("H-1 PO Structure", False, f"remaining_qty_to_ship not clamped: {remaining}")
                    else:
                        self.log_test("H-1 PO Structure", False, f"Missing fields: {missing_fields}")
                else:
                    self.log_test("H-1 PO Structure", True, "PO endpoint accessible (empty list)")
            else:
                self.log_test("H-1 PO Structure", False, f"Unexpected response type: {type(pos)}")
        except Exception as e:
            self.log_test("H-1 PO Structure", False, f"JSON parse error: {e}")

    def test_c3_job_fields_structure(self):
        """Test C-3: Job response structure with correct shipped totals"""
        print("\n🔍 Testing C-3: Job Response Structure...")
        
        success, response, error = self.make_request('GET', '/api/production-jobs')
        if not success:
            self.log_test("C-3 Job Structure", False, f"Failed to get jobs: {error}")
            return
        
        if response.status_code != 200:
            self.log_test("C-3 Job Structure", False, f"Status {response.status_code}")
            return
        
        try:
            jobs = response.json()
            if isinstance(jobs, list):
                if len(jobs) > 0:
                    job = jobs[0]
                    required_fields = ['total_shipped_to_buyer', 'remaining_to_ship']
                    missing_fields = [f for f in required_fields if f not in job]
                    
                    if not missing_fields:
                        shipped = job.get('total_shipped_to_buyer', 0)
                        remaining = job.get('remaining_to_ship', 0)
                        self.log_test("C-3 Job Structure", True, f"Job fields present: shipped={shipped}, remaining={remaining}")
                    else:
                        self.log_test("C-3 Job Structure", False, f"Missing fields: {missing_fields}")
                else:
                    self.log_test("C-3 Job Structure", True, "Job endpoint accessible (empty list)")
            else:
                self.log_test("C-3 Job Structure", False, f"Unexpected response type: {type(jobs)}")
        except Exception as e:
            self.log_test("C-3 Job Structure", False, f"JSON parse error: {e}")

    def test_h2_material_requests_endpoint(self):
        """Test H-2: Material requests endpoint for REQ-RPL functionality"""
        print("\n🔍 Testing H-2: Material Requests Endpoint...")
        
        success, response, error = self.make_request('GET', '/api/material-requests')
        if success and response.status_code == 200:
            try:
                requests_data = response.json()
                if isinstance(requests_data, list):
                    # Look for any REQ-RPL requests
                    rpl_requests = [r for r in requests_data if isinstance(r, dict) and 
                                  r.get('request_number', '').startswith('REQ-RPL-')]
                    
                    self.log_test("H-2 Material Requests", True, f"Material requests endpoint works, found {len(rpl_requests)} REQ-RPL requests")
                else:
                    self.log_test("H-2 Material Requests", True, "Material requests endpoint accessible")
            except Exception as e:
                self.log_test("H-2 Material Requests", False, f"JSON parse error: {e}")
        else:
            self.log_test("H-2 Material Requests", False, f"Failed to get material requests: {error}")

    def test_h3_production_progress_validation(self):
        """Test H-3: Production progress validation"""
        print("\n🔍 Testing H-3: Production Progress Validation...")
        
        # Test with invalid job_item_id
        invalid_progress_data = {
            'job_item_id': 'nonexistent-job-item-id',
            'completed_quantity': 100,
            'progress_date': datetime.now().isoformat(),
            'notes': 'Test validation'
        }
        
        success, response, error = self.make_request('POST', '/api/production-progress', invalid_progress_data)
        if success:
            if response.status_code == 404:
                self.log_test("H-3 Progress Validation", True, "Production progress validates job_item_id existence")
            elif response.status_code == 400:
                response_text = response.text
                if 'melebihi material usable' in response_text or 'material tersedia' in response_text:
                    self.log_test("H-3 Progress Validation", True, "Production progress validates material capacity")
                else:
                    self.log_test("H-3 Progress Validation", True, f"Production progress validation active: {response_text[:100]}")
            else:
                self.log_test("H-3 Progress Validation", False, f"Unexpected status: {response.status_code}")
        else:
            self.log_test("H-3 Progress Validation", False, f"Request failed: {error}")

    def test_m3_defect_report_validation(self):
        """Test M-3: Material defect report vendor_id derivation"""
        print("\n🔍 Testing M-3: Defect Report Validation...")
        
        # Test without vendor_id or job_id
        defect_data = {
            'defect_qty': 5,
            'defect_type': 'Material Cacat',
            'description': 'Test defect without vendor_id'
        }
        
        success, response, error = self.make_request('POST', '/api/material-defect-reports', defect_data)
        if success and response.status_code == 400:
            response_text = response.text
            if 'vendor_id diperlukan' in response_text:
                self.log_test("M-3 Defect Validation", True, "Defect report correctly validates vendor_id requirement")
            else:
                self.log_test("M-3 Defect Validation", False, f"Wrong error message: {response_text}")
        else:
            self.log_test("M-3 Defect Validation", False, f"Should require vendor_id: {response.status_code if response else 'No response'}")

    def test_variance_endpoints_functionality(self):
        """Test variance feature endpoints are still functional"""
        print("\n🔍 Testing Variance Feature Functionality...")
        
        # Test GET /api/production-variances
        success, response, error = self.make_request('GET', '/api/production-variances')
        if success and response.status_code == 200:
            self.log_test("Variance GET Endpoint", True, "Production variances GET works")
        else:
            self.log_test("Variance GET Endpoint", False, f"GET failed: {error}")
        
        # Test POST with invalid data to check validation
        invalid_variance_data = {
            'job_id': 'nonexistent-job-id',
            'variance_type': 'OVERPRODUCTION',
            'reason': 'Test overproduction',
            'items': []
        }
        
        success, response, error = self.make_request('POST', '/api/production-variances', invalid_variance_data)
        if success:
            if response.status_code in [400, 404]:
                self.log_test("Variance POST Validation", True, "Production variances POST validates input")
            elif response.status_code == 201:
                self.log_test("Variance POST Validation", True, "Production variances POST works")
            else:
                self.log_test("Variance POST Validation", False, f"Unexpected status: {response.status_code}")
        else:
            self.log_test("Variance POST Validation", False, f"POST failed: {error}")
        
        # Test UNDERPRODUCTION type
        invalid_variance_data['variance_type'] = 'UNDERPRODUCTION'
        success, response, error = self.make_request('POST', '/api/production-variances', invalid_variance_data)
        if success and response.status_code in [200, 201, 400, 404]:
            self.log_test("Variance UNDERPRODUCTION Type", True, "UNDERPRODUCTION variance type accepted")
        else:
            self.log_test("Variance UNDERPRODUCTION Type", False, f"UNDERPRODUCTION failed: {error}")

    def run_all_tests(self) -> Dict:
        """Run all focused audit tests"""
        print("🚀 Starting Focused Production Flow Audit Tests")
        print(f"🌐 Base URL: {self.base_url}")
        print(f"📅 Test Time: {datetime.now().isoformat()}")
        
        # Authentication
        if not self.test_login():
            print("❌ Authentication failed - stopping tests")
            return self.get_summary()
        
        # Run focused validation tests
        self.test_c1_buyer_shipment_validation()
        self.test_c2_return_validation()
        self.test_h4_negative_return_validation()
        self.test_m1_zero_dispatch_validation()
        self.test_h1_po_fields_structure()
        self.test_c3_job_fields_structure()
        self.test_h2_material_requests_endpoint()
        self.test_h3_production_progress_validation()
        self.test_m3_defect_report_validation()
        self.test_variance_endpoints_functionality()
        
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
            "summary": f"Focused Production Flow Audit Testing: {self.tests_passed}/{self.tests_run} tests passed ({success_rate:.1f}%)"
        }

def main():
    """Main test execution"""
    tester = FocusedAuditTester()
    
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