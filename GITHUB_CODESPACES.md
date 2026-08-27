# GitHub Codespaces Setup

## Quick Start (One Click)

[![Open in GitHub Codespaces](https://github.com/codespaces/new?template_repository=YOUR_USERNAME/YOUR_REPO&quick=1)](https://github.com/codespaces/new)

## Manual Setup

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial trading strategy code"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

### 2. Create Codespace
1. Go to your repo on GitHub
2. Click "Code" → "Create codespace"
3. Wait for environment to build (~1 minute)

### 3. Install Dependencies
```bash
pip install pandas numpy openpyxl
```

### 4. Run Experiments
```bash
cd Research
python find_profitable_stocks.py
```

## Using DeepSeek via GitHub Models

GitHub Models gives you free access to DeepSeek, GPT-4, and more through GitHub's API.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://models.github.ai/inference",
    api_key=os.environ["GITHUB_TOKEN"]  # Auto-populated!
)

response = client.chat.completions.create(
    model="deepseek/DeepSeek-V3-0324",
    messages=[{"role": "user", "content": "Analyze this trading strategy..."}]
)
```

## Free Tier Limits
- 120 core-hours/month
- 2 simultaneous codespaces
- 15GB disk per codespace

## Alternatives

### Google Colab (GPU)
1. Upload code to Google Drive
2. Open in Colab
3. Install dependencies: `!pip install pandas numpy openpyxl`

### Kaggle Notebooks (GPU)
1. Upload data to Kaggle
2. Create new notebook
3. Run same code

## Tips

1. **Save often** - Codespaces can time out
2. **Use git** - Commit regularly to preserve work
3. **Large files** - Add Data/ to .gitignore (too big for git)
4. **API keys** - Use environment variables, never commit keys

## Troubleshooting

### Import errors
```bash
pip install -r requirements.txt
```

### Out of disk space
```bash
# Remove unused packages
pip uninstall -y pandas numpy openpyxl
pip install pandas numpy  # Minimal install
```
