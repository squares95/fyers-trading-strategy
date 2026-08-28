"""
Test LLM access via Groq (free tier, working setup).
Get API key: https://console.groq.com (free, no credit card)
Run: python test_deepseek.py
"""

import os
import sys


def test_python_version():
    """Verify Python is available."""
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print()


def test_api_key():
    """Check if GROQ_API_KEY is available."""
    token = os.environ.get("GROQ_API_KEY", "")
    if token:
        print(f"✓ GROQ_API_KEY is set (length: {len(token)})")
        return True
    else:
        print("✗ GROQ_API_KEY is NOT set")
        print("  Get a free API key at: https://console.groq.com")
        print("  Then set: export GROQ_API_KEY=your_key (Git Bash)")
        print("           setx GROQ_API_KEY your_key (PowerShell)")
        return False


def test_llm_access():
    """Test Groq with reasoning model."""
    try:
        from openai import OpenAI
    except ImportError:
        print("Installing openai package...")
        os.system("pip install openai")
        from openai import OpenAI

    token = os.environ.get("GROQ_API_KEY", "")
    if not token:
        print("\n⚠️  Cannot test LLM without GROQ_API_KEY")
        return False

    print("\nTesting Groq openai/gpt-oss-120b (free tier)...")
    print("-" * 60)

    try:
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=token)

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": "Reply with exactly: VWAP PULLBACK WORKS"}],
            max_tokens=200,  # Reasoning models need more room
            temperature=0.1,
        )

        content = response.choices[0].message.content or ""
        reasoning = response.choices[0].message.reasoning or ""

        print("✓ LLM response received!")
        print(f"Model: {response.model}")
        print(f"Response: {content}")
        if reasoning:
            print(f"Reasoning: {reasoning[:200]}")
        print()
        return True

    except Exception as e:
        print(f"✗ Error accessing Groq: {e}")
        print()
        print("Possible issues:")
        print("  1. GROQ_API_KEY not set or invalid")
        print("  2. Rate limit hit (free tier)")
        print("  3. Network connectivity issue")
        return False


def list_available_models():
    """List available models on Groq (free tier focus)."""
    try:
        from openai import OpenAI
    except ImportError:
        os.system("pip install openai")
        from openai import OpenAI

    token = os.environ.get("GROQ_API_KEY", "")
    if not token:
        print("Cannot list models without GROQ_API_KEY")
        return

    print("Testing free tier models...")
    print("-" * 60)

    # Free tier verified models (Aug 2026)
    models_to_test = [
        ("openai/gpt-oss-120b", "GPT OSS 120B (reasoning, 30 RPM)"),
        ("openai/gpt-oss-20b", "GPT OSS 20B (faster reasoning)"),
        ("groq/compound", "Groq Compound (70K context, 30 RPM)"),
    ]

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=token)

    for model_id, model_name in models_to_test:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say OK"}],
                max_tokens=200,
            )
            content = response.choices[0].message.content or ""
            print(f"✓ {model_name}: '{content[:40]}'")
        except Exception as e:
            print(f"✗ {model_name}: {str(e)[:80]}")


def main():
    print("=" * 60)
    print("GROQ LLM TEST SCRIPT (Free Tier)")
    print("=" * 60)
    print()

    test_python_version()
    test_api_key()

    if test_llm_access():
        list_available_models()

    print()
    print("=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print()
    print("1. Download data for testing:")
    print("   python download_new_stocks.py")
    print()
    print("2. Run strategy tests:")
    print("   cd Research")
    print("   python test_tatapower.py")
    print()
    print("3. Use LLM to analyze results:")
    print('   python -c "from test_deepseek import *"')
    print()


if __name__ == "__main__":
    main()
