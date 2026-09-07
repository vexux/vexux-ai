# Fix for Recovery Task ID Preservation in Vexux-AI

## Summary
Fixed the issue where recovery tasks were not preserving the failed task ID, causing the error:
```
Planning failed: Recovery task must preserve the failed task id.
```

## Root Cause Analysis
The recovery prompt in the Planner was not explicit enough about the requirement to preserve the failed task ID. The model could interpret the task ID in the template as an example or suggestion rather than an absolute requirement, leading it to generate a new task ID instead of preserving the original one.

## Changes Made

### 1. Enhanced Recovery Prompt in `agent/planner.py` (Lines 310-359)

**Before:**
- The recovery prompt showed the failed task ID but didn't explicitly state it must be preserved
- The instruction was: "Create exactly one recovery task for the failed task below."
- Only mentioned "Do not recreate tasks that already completed successfully."

**After:**
- Added explicit statement: "CRITICAL: The recovered task MUST have the exact same task ID as the failed task."
- Added: "Do not generate a new task ID."
- Changed "Failed task ID:" to "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):" to highlight the requirement
- Added a new "CRITICAL REQUIREMENTS:" section that explicitly states:
  - "The task ID "{failed_task.id}" in the JSON output MUST be exactly this value."
  - "Do not modify, replace, or regenerate the task ID."

### 2. Updated Test Handlers in `test_multi_task_failure.py`

Updated all mock model gateway handlers to use the new prompt pattern:
- Changed from: `"Failed task ID:\n{task_id}"`
- Changed to: `"Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\n{task_id}"`

Affected tests:
- `test_first_task_fails_and_recovers()` (Line 202-204)
- `test_second_task_fails_after_first_succeeds()` (Line 244-246)
- `test_successful_tasks_are_not_unnecessarily_repeated()` (Line 309-311)
- `test_replanning_stops_after_retry_limit()` (Line 336-338)
- `test_final_response_preserves_successful_results()` (Line 366-368)

### 3. Updated Evaluation Runner in `evaluation/runner.py`

**Initial planning detection (Lines 97-104):**
- Added condition to exclude recovery prompts from matching the initial planning condition
- Changed: `"planning component for an AI agent" in prompt`
- To: `("planning component for an AI agent" in prompt and "recovery" not in prompt)`

**Recovery planning detection (Lines 106-126):**
- Changed detection from: `"You are replanning an agent task"`
- To: `"structured recovery-planning component"`
- Updated prompt parsing to use new pattern:
  - Changed from: `prompt.split("Failed task ID:\n", 1)[1]`
  - To: `prompt.split("Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\n", 1)[1]`

### 4. Added New Regression Test: `test_task_id_preservation.py`

New comprehensive test file that verifies:
1. `test_recovery_prompt_explicitly_states_task_id_preservation()`
   - Verifies the recovery prompt contains all critical requirements
   - Confirms task ID is preserved in recovery tasks
   - Validates prompt text mentions "MUST preserve", "Do not generate new ID", etc.

2. `test_recovery_validates_task_id_match()`
   - Confirms validation catches mismatched task IDs
   - Ensures the ValueError is raised with appropriate message

3. `test_recovery_works_with_multiple_task_ids()`
   - Tests recovery works with various task ID formats
   - Covers edge cases like "task_1", "task_abc_xyz", etc.

### 5. Added Optional Live Test: `test_mistral_recovery.py`

Test file for validating the fix works with the actual Mistral API:
- Skips if MISTRAL_API_KEY is not set
- Tests the scenario "What is EC2 and calculate abc" which triggered the original error
- Verifies recovery occurs and trace shows failed task recovery

## Testing Results

### Unit Tests (test_multi_task_failure.py)
```
Results: 8 passed, 0 failed out of 8 tests.
✓ test_single_successful_task
✓ test_multiple_successful_tasks
✓ test_first_task_fails_and_recovers
✓ test_second_task_fails_after_first_succeeds
✓ test_replanning_receives_failed_task
✓ test_successful_tasks_are_not_unnecessarily_repeated
✓ test_replanning_stops_after_retry_limit
✓ test_final_response_preserves_successful_results
```

### Task ID Preservation Tests (test_task_id_preservation.py)
```
Results: 7 tests passed
✓ Recovery prompt explicitly states task ID preservation requirement
✓ Recovery task successfully preserves failed task ID
✓ Recovery validation correctly rejects mismatched task IDs
✓ Recovery preserves task ID: task_1
✓ Recovery preserves task ID: task_2
✓ Recovery preserves task ID: task_3
✓ Recovery preserves task ID: task_abc_xyz
```

## Expected Behavior After Fix

For the query "What is EC2 and calculate abc":

```
Initial planning
        ↓
Task 1 (retrieval): Retrieve EC2 information → SUCCESS
        ↓
Task 2 (calculator): Calculate "abc" → FAILURE (invalid expression)
        ↓
Observer records failure with task_id="task_2"
        ↓
DecisionMaker requests recovery
        ↓
Planner creates recovery task
  - ID: "task_2" (PRESERVED from failed task)
  - Capability: "model" (changed from "tool")
  - Input: Alternative recovery approach
        ↓
Recovery task executes successfully
        ↓
ResponseSynthesizer produces final answer
        ↓
Return SUCCESS with combined results
```

## Key Improvements

1. **Explicit Requirements**: The recovery prompt now uses multiple mechanisms to communicate the requirement:
   - Direct statement: "CRITICAL: The recovered task MUST have the exact same task ID"
   - Example template showing the exact ID
   - Critical requirements section with specific statement
   - Column highlighting in header: "YOU MUST PRESERVE THIS EXACT ID"

2. **Model Compliance**: The enhanced prompt makes it significantly clearer for both small and large language models that the task ID must not be changed.

3. **Backward Compatibility**: All existing tests pass, and the architectural flow remains unchanged.

4. **Validation Preserved**: The validation at line 364-365 of planner.py still correctly rejects mismatched IDs, ensuring the system catches any issues.

## Files Modified

1. `agent/planner.py` - Enhanced recovery prompt
2. `test_multi_task_failure.py` - Updated test handlers for new prompt pattern
3. `evaluation/runner.py` - Updated prompt detection and parsing

## Files Added

1. `test_task_id_preservation.py` - New comprehensive regression tests
2. `test_mistral_recovery.py` - Optional live Mistral API test

## Verification Steps

To verify the fix:

1. Run unit tests:
   ```bash
   python test_multi_task_failure.py
   ```

2. Run task ID preservation tests:
   ```bash
   python test_task_id_preservation.py
   ```

3. Run with Mistral API (requires MISTRAL_API_KEY):
   ```bash
   python test_mistral_recovery.py
   ```

4. Run full pytest suite (requires all dependencies):
   ```bash
   python -m pytest -v
   ```
