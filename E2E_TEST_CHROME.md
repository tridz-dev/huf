# End-to-End Testing Guide - Flow Engine in Chrome

## Test Setup

**Date:** 2026-03-27  
**Branch:** feature/flow-backend-integration  
**Server:** http://localhost:8101  
**Test Flow ID:** chrome-test-flow-001

---

## Test Flows Created via API

### Flow 1: Simple Agent Execution
```json
{
  "flow_id": "chrome-test-flow-001",
  "flow_name": "Chrome Test - Simple Agent",
  "nodes": [
    {"id": "start", "type": "agent.run", "config": {"agent_name": "nivo"}}
  ],
  "edges": []
}
```

### Flow 2: Multi-Step with Router
```json
{
  "flow_id": "chrome-test-flow-002", 
  "flow_name": "Chrome Test - Router Flow",
  "nodes": [
    {"id": "input", "type": "agent.run", "config": {"agent_name": "nivo"}},
    {"id": "router", "type": "router.llm", "config": {}},
    {"id": "branch-a", "type": "agent.run", "config": {"agent_name": "nivo"}},
    {"id": "end", "type": "end"}
  ],
  "edges": [
    {"from": "input", "to": "router", "type": "always"},
    {"from": "router", "to": "branch-a", "type": "on_success"},
    {"from": "branch-a", "to": "end", "type": "always"}
  ]
}
```

---

## Manual Testing Steps in Chrome

### Step 1: Access Huf AI Platform
```
URL: http://localhost:8101/login
Username: Administrator
Password: admin
```

### Step 2: Navigate to Flows
```
http://localhost:8101/huf/flows
```

### Step 3: Verify Test Flows Appear
Look for:
- "Chrome Test - Simple Agent" 
- "Chrome Test - Router Flow"

### Step 4: Open Flow Canvas
Click on "Chrome Test - Simple Agent" to open the flow editor.

### Step 5: Check Flow Details
Expected to see:
- Flow canvas with nodes
- Node configuration panel
- Run button

### Step 6: Execute Flow
Click "Run" button and observe:
- Flow Run creation
- Execution status
- Results

---

## Screenshots to Capture

1. **Login Page** - Verify accessibility
2. **Flows List** - Verify test flows visible
3. **Flow Canvas** - Verify visual editor
4. **Node Config** - Verify configuration panel
5. **Flow Run Results** - Verify execution
6. **Flow Run DocType** - Backend verification

---

## API Commands (for reference)

### Create Test Flow
```bash
curl -c /tmp/cookies.txt -X POST http://localhost:8101/api/method/login \
  -d "usr=Administrator&pwd=admin"

curl -b /tmp/cookies.txt -X POST \
  http://localhost:8101/api/method/huf.ai.flow_api.save_flow_definition \
  -H "Content-Type: application/json" \
  -d '{
    "flow_id": "chrome-test-flow-001",
    "flow_name": "Chrome Test - Simple Agent",
    "definition_json": {
      "schema_version": 1,
      "id": "chrome-test-flow-001",
      "version": 1,
      "entry": "start",
      "nodes": [{"id": "start", "type": "agent.run", "config": {"agent_name": "nivo"}}],
      "edges": [],
      "settings": {"mode": "normal"},
      "metadata": {"test": true}
    }
  }'
```

### Activate Flow
```bash
docker exec fdocker_devcontainer-frappe-1 bash -c \
  'bench --site huf.localhost mariadb <<< "UPDATE \`tabFlow Definition\` SET status = '\''Active'\'' WHERE flow_id = '\''chrome-test-flow-001'\''"'
```

### Run Flow
```bash
curl -b /tmp/cookies.txt -X POST \
  http://localhost:8101/api/method/huf.ai.flow_api.run_flow \
  -d '{"flow_id": "chrome-test-flow-001", "payload": {"test": "chrome"}}'
```

---

## Expected Results

### UI Elements
- [ ] Flow list loads with test flows
- [ ] Canvas renders nodes correctly
- [ ] Node configuration panel opens
- [ ] Run button triggers execution
- [ ] Flow Run status updates

### Backend Data
- [ ] Flow Definition created
- [ ] Flow Run created with status
- [ ] Agent Run linked
- [ ] Context preserved

---

## Troubleshooting

### If flows don't appear in UI:
1. Check Flow Definition exists in DB
2. Verify status is "Active" 
3. Refresh browser cache (Ctrl+Shift+R)

### If canvas doesn't load:
1. Check browser console for errors
2. Verify frontend build completed
3. Check network tab for API failures

### If flow execution fails:
1. Check Flow Run status via API
2. Verify nivo agent is active
3. Check error_message field

---

## Test Checklist

- [ ] Login successful
- [ ] Flows page accessible
- [ ] Test flows visible in list
- [ ] Flow canvas opens
- [ ] Nodes display correctly
- [ ] Run button works
- [ ] Execution completes
- [ ] Results visible
