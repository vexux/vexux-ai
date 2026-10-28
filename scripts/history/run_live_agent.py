"""Live smoke test for the recovery task ID preservation fix."""

import json
from core.contracts.execution import Task, Plan
from core.tools.registry import ToolRegistry
from core.tools.calculator import CalculatorTool
from core.context.context_manager import ContextManager
from agent.observer import Observer
from agent.decision import DecisionMaker
from agent.execution_manager import ExecutionManager
from agent.planner import Planner
from agent.response_synthesizer import ResponseSynthesizer
from agent.agent import Agent


class DeterministicModelGateway:
    """Deterministic model gateway for smoke testing."""

    def __init__(self):
        self.prompts = []
        self.handlers = {}

    def set_response_for(self, pattern: str, response: str):
        self.handlers[pattern] = response

    def generate(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        # Check handlers in reverse order (most specific first)
        for pattern in sorted(self.handlers.keys(), key=len, reverse=True):
            if pattern in prompt:
                return self.handlers[pattern]
        # Default fallback
        return '{"tasks": [{"id": "task_default", "description": "default", "capability": "model", "input": {"query": "default"}}]}'


class DeterministicRetrieval:
    """Deterministic retrieval for smoke testing."""

    def ask(self, query: str) -> str:
        if "EC2" in query or "ec2" in query.lower():
            return "Amazon EC2 is a web service providing resizable compute capacity in the cloud."
        return f"Retrieved information about: {query}"


def test_query(agent, query, description):
    """Test a single query and report results."""
    print("\n" + "=" * 70)
    print(f"TEST: {description}")
    print("=" * 70)
    print(f"Query: {query}")
    
    result = agent.run(query)
    
    print(f"\nSuccess: {result.success}")
    if result.output:
        print(f"Output: {result.output[:200]}...")
    if result.error:
        print(f"Error: {result.error}")
    
    print(f"Trace length: {len(result.trace)}")
    for i, obs in enumerate(result.trace):
        status = "[OK]" if obs.success else "[FAIL]"
        print(f"  Step {i+1}: {status} task_id={obs.task_id}")
        if obs.error:
            print(f"         Error: {obs.error}")
    
    return result


def main():
    """Run live smoke tests."""
    
    print("\n" + "=" * 70)
    print("LIVE SMOKE TEST: Recovery Task ID Preservation Fix")
    print("=" * 70)
    
    # Create mock infrastructure
    gateway = DeterministicModelGateway()
    retrieval = DeterministicRetrieval()
    tool_registry = ToolRegistry()
    tool_registry.register(CalculatorTool())
    
    # Register deterministic responses
    
    # Test 1: Simple retrieval
    gateway.set_response_for(
        "What is EC2?",
        json.dumps({"tasks": [
            {"id": "task_1", "description": "Retrieve EC2 info", "capability": "retrieval", "input": {"query": "What is EC2?"}},
        ]})
    )
    
    # Test 2: Simple calculation
    gateway.set_response_for(
        "Calculate 24 * 7",
        json.dumps({"tasks": [
            {"id": "task_1", "description": "Calculate", "capability": "tool", "input": {"tool": "calculator", "arguments": {"expression": "24 * 7"}}},
        ]})
    )
    
    # Test 3: Multi-task with valid calculation
    gateway.set_response_for(
        "What is EC2 and calculate 24 * 7",
        json.dumps({"tasks": [
            {"id": "task_1", "description": "Retrieve EC2", "capability": "retrieval", "input": {"query": "What is EC2?"}},
            {"id": "task_2", "description": "Calculate", "capability": "tool", "input": {"tool": "calculator", "arguments": {"expression": "24 * 7"}}},
        ]})
    )
    
    # Test 4: Multi-task with invalid calculation (recovery test)
    gateway.set_response_for(
        "What is EC2 and calculate abc",
        json.dumps({"tasks": [
            {"id": "task_1", "description": "Retrieve EC2", "capability": "retrieval", "input": {"query": "What is EC2?"}},
            {"id": "task_2", "description": "Calculate", "capability": "tool", "input": {"tool": "calculator", "arguments": {"expression": "abc"}}},
        ]})
    )
    
    # Recovery task for invalid calculation - CRITICAL TEST
    gateway.set_response_for(
        "Failed task ID (YOU MUST PRESERVE THIS EXACT ID):\ntask_2",
        json.dumps({"tasks": [
            {"id": "task_2", "description": "Recovery: model response", "capability": "model", "input": {"query": "What does 'abc' mean in the context of calculations?"}},
        ]})
    )
    
    # Synthesis responses
    gateway.set_response_for(
        "synthesizing",
        "Synthesized response combining all results."
    )
    
    # Build agent
    execution_manager = ExecutionManager(
        retrieval=retrieval,
        tool_registry=tool_registry,
        model_gateway=gateway,
    )
    
    planner = Planner(
        model_gateway=gateway,
        tool_registry=tool_registry,
    )
    
    agent = Agent(
        execution_manager=execution_manager,
        planner=planner,
        observer=Observer(),
        decision_maker=DecisionMaker(),
        context_manager=ContextManager(),
        response_synthesizer=ResponseSynthesizer(model_gateway=gateway),
    )
    
    # Run tests
    results = []
    
    try:
        result1 = test_query(agent, "What is EC2?", "Simple retrieval task")
        results.append(("What is EC2?", result1.success))
    except Exception as e:
        print(f"Test 1 failed: {e}")
        results.append(("What is EC2?", False))
    
    try:
        result2 = test_query(agent, "Calculate 24 * 7", "Simple calculation task")
        results.append(("Calculate 24 * 7", result2.success))
    except Exception as e:
        print(f"Test 2 failed: {e}")
        results.append(("Calculate 24 * 7", False))
    
    try:
        result3 = test_query(agent, "What is EC2 and calculate 24 * 7", "Multi-task with valid calculation")
        results.append(("What is EC2 and calculate 24 * 7", result3.success))
    except Exception as e:
        print(f"Test 3 failed: {e}")
        results.append(("What is EC2 and calculate 24 * 7", False))
    
    try:
        result4 = test_query(agent, "What is EC2 and calculate abc", "Multi-task with invalid calculation (recovery test)")
        results.append(("What is EC2 and calculate abc", result4.success))
        
        # CRITICAL: Verify recovery task preserved ID
        if len(result4.trace) >= 3:
            print("\n[CRITICAL VERIFICATION]")
            print(f"  Recovery occurred: {result4.trace[1].success} -> {result4.trace[2].success}")
            print(f"  Failed task ID preserved: {result4.trace[1].task_id} -> {result4.trace[2].task_id}")
            if result4.trace[1].task_id == result4.trace[2].task_id == "task_2":
                print("  [PASS] Task ID preservation: VERIFIED")
            else:
                print("  [FAIL] Task ID preservation: FAILED")
                results[-1] = ("What is EC2 and calculate abc", False)
    except Exception as e:
        print(f"Test 4 failed: {e}")
        import traceback
        traceback.print_exc()
        results.append(("What is EC2 and calculate abc", False))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for query, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status} {query}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[PASS] All smoke tests passed!")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
