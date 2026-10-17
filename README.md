# Silicon Dreams Video Converter

A no-signup website that converts public YouTube and Facebook video links to
**MP4, WEBM, MKV, AVI** (video) and **MP3, M4A, WAV** (audio).

- Elegant champagne-and-midnight theme with automatic light/dark mode
- Original Silicon Dreams logo (`public/img/logo.svg`)
- Terms & Conditions (`/terms`) and Privacy Policy (`/privacy`)
- SEO: meta tags, Open Graph/Twitter cards, JSON-LD (Organization, WebSite,
  WebApplication, FAQPage), `sitemap.xml`, `robots.txt`, web manifest, 404 page
- Privacy: files are deleted right after download, no database, no cookies
- Protection: URL whitelist (YouTube/Facebook only), per-IP rate limit,
  concurrent-job cap, max length/size limits, security headers & CSP

## Files (everything in one folder)
```
app.py              Server + converter (yt-dlp + FFmpeg)
requirements.txt    Python packages
Dockerfile          For hosting
index.html          Home page + converter
terms.html          Terms & Conditions
privacy.html        Privacy Policy
404.html            Page-not-found
style.css           Theme
script.js           Converter + dark-mode button
theme.js            Remembers light/dark choice
logo.svg            Silicon Dreams logo
icon-512.png, apple-touch-icon.png, og-image.png   Icons & share image
robots.txt, sitemap.xml, site.webmanifest          SEO files
```
Only the website files are sent to visitors; app.py and Dockerfile stay private.

## Run locally
Requires Python 3.10+ and FFmpeg (`sudo apt install ffmpeg`, `brew install ffmpeg`,
or download from ffmpeg.org on Windows).
```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000
```

## Deploy (Docker)
```bash
docker build -t silicon-dreams .
docker run -p 8000:8000 silicon-dreams
```
Works on any host that runs Docker (a VPS, Render, Railway, Fly.io, DigitalOcean, etc.).
Put it behind HTTPS (most hosts do this for you). Static-only hosts such as
GitHub Pages or Netlify **cannot** run the converter — it needs a server.

## Before going live — replace placeholders
| Find | Replace with |
|---|---|
| `https://www.example.com` | your real domain (in all HTML files, `robots.txt`, `sitemap.xml`) |
| `support@example.com`, `legal@example.com`, `privacy@example.com` | your real email addresses |
| `[Registered address]` | your company address (terms.html, privacy.html) |
| `[Your Country/State]`, `[Your City]` | governing law & courts (terms.html) |

Then submit `https://yourdomain/sitemap.xml` in Google Search Console and Bing Webmaster Tools.
Have a lawyer review the Terms and Privacy Policy for your jurisdiction.

## Settings (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `PORT` | 8000 | Server port |
| `MAX_DURATION_SECONDS` | 10800 | Longest video accepted (3 h) |
| `MAX_FILESIZE_MB` | 2048 | Largest download |
| `MAX_CONCURRENT_JOBS` | 3 | Simultaneous conversions |
| `RATE_LIMIT_PER_10MIN` | 30 | Requests per IP per 10 minutes |
| `TRUST_PROXY` | 0 (1 in Docker) | Read client IP from `X-Forwarded-For` |

## Keeping it working
YouTube and Facebook change their sites often. Update yt-dlp regularly
(`pip install -U yt-dlp`, or rebuild the Docker image) — weekly is a good habit.
Some hosting IP ranges get blocked by YouTube; if conversions start failing on
a host, check the yt-dlp project's guidance or try a different provider.

## Legal note
Downloading videos may breach a platform's terms of service and, for content
you don't own or have permission to use, copyright law. The site asks users to
confirm they have rights to the content, and the Terms explain user
responsibility and a takedown process. Respond promptly to valid complaints.
