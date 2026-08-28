"""
Test DeepSeek access via GitHub Models in Codespace.

This script verifies that you can use DeepSeek through GitHub's free API.
Run: python test_deepseek.py (NOT py)
"""
import os
import sys


def test_python_version():
    """Verify Python is available."""
    print(f"Python version: {sys.version}")
    print(f"Python executable: {sys.executable}")
    print()


def test_github_token():
    """Check if GITHUB_TOKEN is available."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        print(f"✓ GITHUB_TOKEN is set (length: {len(token)})")
        return True
    else:
        print("✗ GITHUB_TOKEN is NOT set")
        print("  This should be auto-populated in Codespaces.")
        print("  If running locally, you need to set it manually.")
        return False


def test_deepseek_access():
    """Test DeepSeek via GitHub Models."""
    try:
        from openai import OpenAI
    except ImportError:
        print("Installing openai package...")
        os.system("pip install openai")
        from openai import OpenAI

    token = os.environ.get("DEEPSEEK_API_KEY", "")
    if not token:
        print("\n⚠️  Cannot test DeepSeek without DEEPSEEK_API_KEY")
        print("  Get a free API key at: https://platform.deepseek.com")
        print("  Then set: set DEEPSEEK_API_KEY=your_key_here (Windows)")
        print("  Or: export DEEPSEEK_API_KEY=your_key_here (Linux/Mac)")
        return False

    print("\nTesting DeepSeek via Direct API...")
    print("-" * 60)

    try:
        client = OpenAI(
            base_url="https://api.deepseek.com",
            api_key=token
        )

        # Test with DeepSeek V4 Pro
        response = client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[
                {"role": "user", "content": "What is a VWAP pullback strategy in 2 sentences?"}
            ],
            max_tokens=100
        )

        print("✓ DeepSeek response received!")
        print(f"Model: {response.model}")
        print(f"Response: {response.choices[0].message.content}")
        print()
        return True

    except Exception as e:
        print(f"✗ Error accessing DeepSeek: {e}")
        print()
        print("Possible issues:")
        print("  1. DEEPSEEK_API_KEY not set or invalid")
        print("  2. Network connectivity issue")
        print("  3. DeepSeek API temporarily unavailable")
        return False


def list_available_models():
    """List some available models on DeepSeek."""
    try:
        from openai import OpenAI
    except ImportError:
        os.system("pip install openai")
        from openai import OpenAI

    token = os.environ.get("DEEPSEEK_API_KEY", "")
    if not token:
        print("Cannot list models without DEEPSEEK_API_KEY")
        return

    print("Testing different models...")
    print("-" * 60)

    models_to_test = [
        ("deepseek-v4-pro", "DeepSeek V4 Pro"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
    ]

    client = OpenAI(
        base_url="https://api.deepseek.com",
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
    print("DEEPSEEK TEST SCRIPT")
    print("=" * 60)
    print()

    test_python_version()
    test_github_token()  # Keep for backward compatibility

    if test_deepseek_access():
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
    print("3. Use DeepSeek to analyze results:")
    print("   python -c \"from test_deepseek import *\"")
    print()


if __name__ == "__main__":
    main()