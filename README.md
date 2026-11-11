# 🎯 Machine Learning & Data Science Job Tracker Dashboard

An automated tracker and interactive web dashboard for senior Machine Learning, Applied Science, and Data Science roles across India, the UK, and Australia.

## 🚀 Features

- **Interactive Dashboard (`index.html`)**: Filter by location, company, experience fit, and visa sponsorship status.
- **Direct Application Links**: Direct links to official ATS requisitions (Greenhouse, Lever, Ashby, Workday, Microsoft Careers).
- **Automated Telegram Alerts & Tracking**: Consolidated digest notifications sent to subscribed Telegram channels, with `/applied <ID>` and `/skip <ID>` commands.
- **GitHub Pages Ready**: Zero build step required. Automatically deployed via GitHub Actions workflow (`.github/workflows/deploy.yml`).

## 📁 Project Structure

```
job-search-dashboard/
├── .github/workflows/deploy.yml   # Auto-deploys to GitHub Pages
├── index.html                     # Live responsive web dashboard
├── build_site.py                  # Compiles jobs data into index.html
├── data/
│   └── jobs.json                  # Current active roles dataset
├── scripts/                       # Local runner scripts
└── README.md
```

## Hosted pipeline

Crawl, website-mark sync, and Pages publish can run in GitHub Actions so the Windows PC is not required. Schedules, Telegram, and outreach stay off. Canonical JSON stays in a private store, not this public repository. See [docs/HOSTED_MIGRATION.md](docs/HOSTED_MIGRATION.md).

## 🌐 Deploy to GitHub Pages

1. Create a new repository on [GitHub](https://github.com/new).
2. Push this folder to your repository:
   ```bash
   git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
   git branch -M main
   git push -u origin main
   ```
3. In your GitHub repository settings:
   - Navigate to **Settings** > **Pages**.
   - Under **Build and deployment** > **Source**, select **GitHub Actions**.
4. Your dashboard will be live at `https://<YOUR_USERNAME>.github.io/<YOUR_REPO>/`!
