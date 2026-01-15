# Knowledge System Testing Guide

This guide provides step-by-step instructions for testing the Huf Knowledge System Phase 1.

## Prerequisites

1. **Install Dependencies**
   ```bash
   bench setup requirements
   ```
   This will install `llama-index-core` and other required packages.

2. **Run Migrations**
   ```bash
   bench migrate
   ```
   This creates the new DocTypes: `Knowledge Source`, `Knowledge Input`, and `Agent Knowledge`.

3. **Optional Dependencies for File Extraction**
   - PDF: `pip install pypdf` or `pip install PyPDF2`
   - DOCX: `pip install python-docx`
   - URL: `pip install requests beautifulsoup4`

## Step-by-Step Testing Guide

### Step 1: Create a Knowledge Source

1. Navigate to **Knowledge Source** list view
2. Click **New**
3. Fill in the form:
   - **Source Name**: `Test Documentation`
   - **Description**: `Test knowledge source for PDF documents`
   - **Knowledge Type**: `sqlite_fts` (default, only option in Phase 1)
   - **Scope**: `Site` (default)
   - **Chunk Size**: `512` (default)
   - **Chunk Overlap**: `50` (default)
4. Click **Save**

**Expected Result**: 
- Knowledge Source is created with status `Pending`
- SQLite database file is initialized (check `/private/files/knowledge/`)

### Step 2: Add a PDF File Input

1. Open the **Knowledge Source** you just created
2. Navigate to **Knowledge Input** list view
3. Click **New**
4. Fill in the form:
   - **Knowledge Source**: Select `Test Documentation`
   - **Input Type**: `File`
   - **File**: Upload a PDF file (e.g., a product manual, documentation PDF)
5. Click **Save**

**Expected Result**:
- Knowledge Input is created with status `Pending`
- Background job is queued automatically
- Status changes to `Processing` → `Indexed` (check after a few seconds)
- `Chunks Created` field shows number of chunks generated
- `Character Count` shows total characters extracted

**Troubleshooting**:
- If status stays `Pending`, check background job queue: `bench --site [site] console`
- If status is `Error`, check `Error Message` field
- Verify PDF extractor is installed: `pip list | grep -i pdf`

### Step 3: Add Text Input (Alternative)

1. Create another **Knowledge Input**:
   - **Knowledge Source**: `Test Documentation`
   - **Input Type**: `Text`
   - **Text**: Paste some documentation text (e.g., FAQ, instructions)
2. Click **Save**

**Expected Result**: Same as Step 2 - text is chunked and indexed.

### Step 4: Verify Indexing Status

1. Go back to **Knowledge Source** (`Test Documentation`)
2. Check the **Status** section:
   - **Status**: Should be `Ready`
   - **Total Chunks**: Should show total chunks across all inputs
   - **Total Inputs**: Should show number of indexed inputs
   - **Last Indexed At**: Should show timestamp
   - **Index Size (bytes)**: Should show SQLite file size

**Expected Result**: 
- Status is `Ready`
- Statistics are updated correctly
- SQLite file exists at `/private/files/knowledge/test_documentation.sqlite3`

### Step 5: Test Search Directly

1. In **Knowledge Source** form, click **Test Search** button (only visible when status is `Ready`)
2. Enter a search query related to your PDF content (e.g., if PDF is about "installation", search for "install")
3. Set **Top K Results**: `5`
4. Click **Search**

**Expected Result**:
- Results appear showing:
  - Title (from source)
  - Score (BM25 relevance score)
  - Text snippet (first 300 chars)
- Results are ranked by relevance
- Results match your query terms

### Step 6: Link Knowledge Source to an Agent

1. Navigate to **Agent** list view
2. Open an existing agent or create a new test agent
3. Go to **Knowledge** tab
4. Add a row in **Knowledge Sources** table:
   - **Knowledge Source**: `Test Documentation`
   - **Mode**: `Mandatory` (auto-injected) or `Optional` (tool-based)
   - **Priority**: `0` (higher = searched first)
   - **Max Chunks**: `5` (max chunks per search)
   - **Token Budget**: `2000` (max tokens to inject)
5. Click **Save**

**Expected Result**:
- Agent now has access to the knowledge source
- If `Mandatory`: Knowledge will be auto-injected into prompts
- If `Optional`: Agent can use `knowledge_search` tool

### Step 7: Test Agent with Mandatory Knowledge

1. Open the **Agent** you just configured
2. Ensure **Mode** is set to `Mandatory` in the Knowledge Sources table
3. Navigate to **Agent Console** (or use Agent Chat)
4. Enter a test prompt that should benefit from your knowledge:
   ```
   How do I install the product?
   ```
   (Adjust based on your PDF content)

5. Click **Run** or send the message

**Expected Result**:
- Agent response includes information from your knowledge source
- Response is more accurate/complete than without knowledge
- Check **Agent Run** document:
  - **Knowledge Sources Used**: JSON array showing sources accessed
  - **Chunks Injected**: Number of chunks added to prompt

**Verification**:
1. Open the **Agent Run** document
2. Check **Metadata** tab → **Knowledge Usage** section
3. Verify `knowledge_sources_used` contains your source name
4. Verify `chunks_injected` > 0

### Step 8: Test Agent with Optional Knowledge (Tool-Based)

1. Edit the **Agent** Knowledge Sources:
   - Change **Mode** to `Optional`
2. Save the agent
3. Run the agent again with a query:
   ```
   Search the knowledge base for information about troubleshooting
   ```

**Expected Result**:
- Agent uses `knowledge_search` tool (visible in tool calls)
- Agent retrieves relevant chunks from knowledge source
- Agent cites the source in its response
- Response includes information from knowledge base

**Verification**:
1. Check **Agent Run** → **Agent Tool Call** child table
2. Look for `knowledge_search` tool call
3. Verify tool result contains search results

### Step 9: Test Rebuild Index

1. Go to **Knowledge Source** (`Test Documentation`)
2. Click **Rebuild Index** button
3. Confirm the action

**Expected Result**:
- Status changes to `Rebuilding`
- Background job processes all inputs again
- Status returns to `Ready` when complete
- All chunks are regenerated

**Use Cases**:
- After changing chunk_size or chunk_overlap settings
- After fixing extraction errors
- To refresh corrupted indexes

### Step 10: Test Multiple Knowledge Sources

1. Create a second **Knowledge Source**: `Product FAQs`
2. Add some text inputs with FAQ content
3. Wait for indexing to complete
4. Add both sources to an agent:
   - `Test Documentation` (Mandatory, Priority: 1)
   - `Product FAQs` (Mandatory, Priority: 0)

**Expected Result**:
- Agent searches both sources
- Higher priority source searched first
- Results combined and ranked across sources
- Both sources appear in `knowledge_sources_used`

## Advanced Testing

### Test Deduplication

1. Try adding the same file/text twice to a Knowledge Source
2. **Expected**: Second attempt should fail with "This content already exists" error
3. Verify using `source_hash` field for deduplication

### Test Error Handling

1. Upload a corrupted PDF file
2. **Expected**: Status becomes `Error` with error message
3. Check error details in `Error Message` field
4. Try **Reprocess Input** action to retry

### Test Concurrent Indexing

1. Add multiple inputs simultaneously
2. **Expected**: Redis lock prevents conflicts
3. All inputs process successfully (may take longer)

### Test Search Performance

1. Add a large PDF (100+ pages)
2. Measure search latency for various queries
3. **Expected**: SQLite FTS5 provides fast keyword search (<100ms typically)

## Troubleshooting

### Issue: Status Stays "Pending"

**Solution**:
- Check background job queue: `bench --site [site] console`
- Verify Redis is running: `redis-cli ping`
- Check for errors in logs: `bench --site [site] logs`

### Issue: PDF Extraction Fails

**Solution**:
- Install PDF library: `pip install pypdf`
- Check file is valid PDF
- Try with a different PDF file
- Check error message in Knowledge Input

### Issue: Search Returns No Results

**Solution**:
- Verify Knowledge Source status is `Ready`
- Check `Total Chunks` > 0
- Try broader search terms
- Verify query doesn't contain special FTS5 characters
- Test search directly using "Test Search" button

### Issue: Agent Doesn't Use Knowledge

**Solution**:
- Verify Knowledge Source is linked to Agent
- Check Mode is correct (Mandatory vs Optional)
- For Optional: Verify agent has `knowledge_search` tool available
- Check Agent Run for knowledge usage tracking
- Verify Knowledge Source status is `Ready`

### Issue: Chunking Produces Too Many/Few Chunks

**Solution**:
- Adjust `chunk_size` in Knowledge Source (default: 512)
- Adjust `chunk_overlap` (default: 50)
- Rebuild index after changing settings
- Larger chunk_size = fewer chunks, more context per chunk

## Performance Benchmarks

### Expected Performance (SQLite FTS5)

- **Indexing**: ~100-500 chunks/second
- **Search**: <100ms for queries on 10K chunks
- **File Size**: ~1-2KB per chunk (SQLite overhead)

### Scaling Limits (Phase 1)

- **Recommended**: <100K chunks per Knowledge Source
- **Maximum**: ~1M chunks (SQLite FTS5 limit)
- **Multiple Sources**: No limit (each source is separate SQLite file)

## Next Steps

After successful testing:

1. **Production Setup**:
   - Create knowledge sources for your use cases
   - Add production documentation/files
   - Link to agents that need knowledge

2. **Monitoring**:
   - Check `Agent Run` documents for knowledge usage
   - Monitor indexing job queue
   - Review error logs regularly

3. **Optimization**:
   - Tune chunk_size based on your content
   - Adjust max_chunks per agent based on token budgets
   - Use priority to control search order

## Example Test Scenario

**Scenario**: Customer Support Agent with Product Documentation

1. **Knowledge Source**: `Product Manual`
   - Upload PDF: `product-manual-v2.pdf`
   - Wait for indexing (status: Ready, ~500 chunks)

2. **Agent**: `Customer Support Bot`
   - Link Knowledge Source: `Product Manual` (Mandatory, Priority: 1)
   - Max Chunks: 5, Token Budget: 2000

3. **Test Query**: "How do I reset the device?"
   - Agent response includes relevant section from manual
   - Response cites source
   - Agent Run shows knowledge usage

4. **Verify**: Check Agent Run → Knowledge Sources Used = `["Product Manual"]`

---

**Questions or Issues?** Check the architecture documentation or open an issue on GitHub.
