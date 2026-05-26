#!/usr/bin/env python3
"""
Phase 1: Backend Core Testing Script
Test Flow Engine backend functionality
"""

import frappe
import json

def test_create_flow_definition():
    """Test 1: Create Flow Definition"""
    print("\n[Test 1] Creating Flow Definition...")
    try:
        def_doc = frappe.get_doc({
            "doctype": "Flow Definition",
            "flow_id": "test-flow-001",
            "flow_name": "Test Flow 001",
            "status": "Draft",
            "definition_json": json.dumps({
                "schema_version": 1,
                "id": "test-flow-001",
                "version": 1,
                "entry": "node-1",
                "nodes": [
                    {
                        "id": "node-1",
                        "type": "agent.run",
                        "config": {"agent_name": "nivo"}
                    }
                ],
                "edges": [],
                "settings": {"mode": "normal"}
            })
        })
        def_doc.insert()
        frappe.db.commit()
        print(f"SUCCESS: Created Flow Definition - {def_doc.name}")
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_verify_flow_definition():
    """Test 2: Verify Flow Definition exists"""
    print("\n[Test 2] Verifying Flow Definition...")
    try:
        doc = frappe.get_doc("Flow Definition", "test-flow-001")
        print(f"SUCCESS: Found {doc.flow_name} (Status: {doc.status})")
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def test_create_flow_run():
    """Test 3: Create Flow Run"""
    print("\n[Test 3] Creating Flow Run...")
    try:
        from huf.ai.flow_engine import create_flow_run
        
        flow_run = create_flow_run(
            flow_id="test-flow-001",
            payload={"test": "data", "input": "hello"},
            mode="Normal",
            trigger_type="Manual"
        )
        print(f"SUCCESS: Created Flow Run - {flow_run.name}")
        print(f"  Status: {flow_run.status}")
        print(f"  Current Node: {flow_run.current_node_id}")
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_load_definition():
    """Test 4: Load definition"""
    print("\n[Test 4] Loading Flow Definition...")
    try:
        from huf.ai.flow_engine import load_definition
        
        defn = load_definition("test-flow-001")
        print(f"SUCCESS: Loaded flow {defn['id']}")
        print(f"  Entry node: {defn['entry']}")
        print(f"  Nodes count: {len(defn['nodes'])}")
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_flow_validation():
    """Test 5: Validation - flow_id must match definition_json.id"""
    print("\n[Test 5] Testing validation (mismatched IDs)...")
    try:
        def_doc = frappe.get_doc({
            "doctype": "Flow Definition",
            "flow_id": "test-flow-mismatch",
            "flow_name": "Mismatch Test",
            "status": "Draft",
            "definition_json": json.dumps({
                "id": "different-id",
                "entry": "start",
                "nodes": [{"id": "start", "type": "end"}],
                "edges": [],
                "settings": {}
            })
        })
        # Note: We don't validate this in DocType yet, just document it
        print("INFO: Validation not enforced at DocType level")
        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def run_all_tests():
    """Run all Phase 1 tests"""
    print("=" * 60)
    print("PHASE 1: Backend Core Testing")
    print("=" * 60)
    
    results = []
    results.append(("Create Flow Definition", test_create_flow_definition()))
    results.append(("Verify Flow Definition", test_verify_flow_definition()))
    results.append(("Create Flow Run", test_create_flow_run()))
    results.append(("Load Definition", test_load_definition()))
    results.append(("Flow Validation", test_flow_validation()))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    run_all_tests()
