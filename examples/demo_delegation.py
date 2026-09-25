"""Example script demonstrating autonomous task delegation to OpenRouter models."""

import asyncio
from src.server import workforce_audit_diff, workforce_delegate


async def main() -> None:
    print("Delegating code generation task to workforce...")
    result = await workforce_delegate(
        task_prompt=(
            "Create a utility file named 'demo_math.py' with static helper functions "
            "for calculating prime numbers and factorial, with strict type hints and docstrings."
        ),
        model="qwen/qwen-2.5-coder-32b-instruct",
        timeout_seconds=90,
    )
    print("\n--- Delegation Summary ---")
    print(result)

    print("\n--- Auditing Workspace Diff ---")
    diff = workforce_audit_diff()
    print(diff[:500] if diff else "No changes detected.")


if __name__ == "__main__":
    asyncio.run(main())
