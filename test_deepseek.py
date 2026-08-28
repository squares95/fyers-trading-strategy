"""
Test LLM access via Groq API (free tier).
Get API key: https://console.groq.com (free, no credit card)
Run: python test_deepseek.py (NOT py)
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
        print("  Then set: export GROQ_API_KEY=your_key (Linux/Mac)")
        print("           setx GROQ_API_KEY your_key (Windows)")
        return False


def test_llm_access():
    """Test Llama via Groq."""
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

    print("\nTesting Llama via Groq (free tier)...")
    print("-" * 60)

    try:
        client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=token
        )

        # Test with Llama 3.3 70B via Groq (free)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "What is a VWAP pullback strategy in 2 sentences?"}
            ],
            max_tokens=100
        )

        print("✓ Llama response received!")
        print(f"Model: {response.model}")
        print(f"Response: {response.choices[0].message.content}")
        print()
        return True

    except Exception as e:
        print(f"✗ Error accessing Groq: {e}")
        print()
        print("Possible issues:")
        print("  1. GROQ_API_KEY not set or invalid")
        print("  2. Rate limit hit (Groq free tier has limits)")
        print("  3. Network connectivity issue")
        return False


def list_available_models():
    """List available models on Groq."""
    try:
        from openai import OpenAI
    except ImportError:
        os.system("pip install openai")
        from openai import OpenAI

    token = os.environ.get("GROQ_API_KEY", "")
    if not token:
        print("Cannot list models without GROQ_API_KEY")
        return

    print("Testing different models...")
    print("-" * 60)

    models_to_test = [
        ("llama-3.3-70b-versatile", "Llama 3.3 70B (fast, versatile)"),
        ("llama-3.1-8b-instant", "Llama 3.1 8B (fastest)"),
        ("mixtral-8x7b-32768", "Mixtral 8x7B"),
        ("gemma2-9b-it", "Gemma 2 9B"),
    ]

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=token
    )

    for model_id, model_name in models_to_test:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Say 'OK'"}],
                max_tokens=10
            )
            print(f"✓ {model_name} ({model_id}): {response.choices[0].message.content}")
        except Exception as e:
            print(f"✗ {model_name} ({model_id}): {str(e)[:80]}")


def main():
    print("=" * 60)
    print("GROQ LLM TEST SCRIPT")
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
    print("   python -c \"from test_deepseek import *\"")
    print()


if __name__ == "__main__":
    main()
