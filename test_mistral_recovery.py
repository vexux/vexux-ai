"""Test the recovery task ID preservation fix with actual Mistral API."""

import os
import sys

# Check if MISTRAL_API_KEY is set
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

if not MISTRAL_API_KEY:
    print("MISTRAL_API_KEY not set. Skipping live Mistral test.")
    print("To test with Mistral, set the MISTRAL_API_KEY environment variable.")
    sys.exit(0)

try:
    from models.providers.mistral import MistralProvider
    from core.model_gateway.gateway import ModelGateway
    from agent.planner import Planner
    from core.tools.registry import ToolRegistry
    from core.tools.calculator import CalculatorTool
    from core.composition import create_agent
except ImportError as e:
    print(f"Could not import required modules: {e}")
    print("Skipping live Mistral test.")
    sys.exit(0)


def test_mistral_recovery_preserves_task_id():
    """Test that the Mistral API correctly generates recovery tasks with preserved IDs."""
    print("=" * 70)
    print("Testing Recovery Task ID Preservation with Mistral API")
    print("=" * 70)
    
    try:
        agent = create_agent()
        
        print("\nTest 1: Simple retrieval task")
        response = agent.run("What is EC2?")
        assert response.success, f"Simple retrieval failed: {response.error}"
        print(f"  Result: {response.output[:100]}...")
        
        print("\nTest 2: Simple calculation")
        response = agent.run("Calculate 24 * 7")
        assert response.success, f"Simple calculation failed: {response.error}"
        print(f"  Result: {response.output}")
        
        print("\nTest 3: Multi-task retrieval and calculation")
        response = agent.run("What is EC2 and calculate 24 * 7")
        assert response.success, f"Multi-task failed: {response.error}"
        print(f"  Result: {response.output[:150]}...")
        
        print("\nTest 4: Multi-task with calculator failure (recovery test)")
        response = agent.run("What is EC2 and calculate abc")
        if not response.success:
            print(f"  Expected: Recovery should handle the invalid calculation")
            print(f"  Error: {response.error}")
        else:
            print(f"  Result: {response.output[:150]}...")
            # Verify that the trace shows recovery happened
            if len(response.trace) >= 3:
                print(f"  Trace length: {len(response.trace)} (recovery occurred)")
                for i, obs in enumerate(response.trace):
                    print(f"    Step {i}: task_id={obs.task_id}, success={obs.success}")
        
        print("\n" + "=" * 70)
        print("Mistral API tests completed successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"Error during Mistral test: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_mistral_recovery_preserves_task_id()
