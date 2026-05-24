# ShareStill — Pitch

---

## Elevator Pitch (15s)

> ShareStill delivers church audio, video, and written content directly to your congregation's phone — no app stores, no email newsletters, no social media algorithms. One broadcast reaches everyone on Telegram, WhatsApp, and web simultaneously.

---

## One-Pager

### What

ShareStill is a content distribution platform for churches and faith communities. It lets you upload a single clip (audio, video, or text) and broadcast it to every subscriber — across Telegram, web, and WhatsApp — with zero setup on their end.

### The Problem

Churches produce rich media every week — sermons, prophecies, testimonies, reels — but have no reliable way to get it in front of their people. Social media algorithms bury it. Email goes unread. Building a custom app costs thousands and nobody installs it.

### The Solution

ShareStill is a drop-in solution: deploy the bot, share the link, and every piece of content lands in your subscribers' chat. No installs. No accounts. No algorithm.

### Key Features

- **One-click broadcast** — Send to all subscribers or select specific recipients
- **Multi-format** — Audio, video, text, and file clips
- **Multi-platform** — Telegram bot, web dashboard, WhatsApp broadcast
- **Prophecy Bank** — Personal vault where members save prophecies and testimonies
- **Queue system** — Background processing for large files + scheduled delivery
- **Admin panel** — Web dashboard with subscriber management, analytics, content library
- **Google Drive fallback** — Files >45MB auto-upload to Drive, link sent instead

### Traction

- Live at `sharestill.paperlinkos.site`
- Two admin users, growing subscriber base
- Supports YouTube, Instagram, Google Drive, Vimeo, Twitter/X, SoundCloud + 1000+ sites via yt-dlp

---

## Pitch Deck Outline (10 slides)

| Slide | Title | Content |
|-------|-------|---------|
| 1 | **Cover** | ShareStill — Deliver Content That Lands |
| 2 | **Problem** | Churches create great content, but it dies in the algorithm |
| 3 | **Solution** | One broadcast. Every subscriber. Every platform. |
| 4 | **How It Works** | Upload → Click broadcast → Subscribers get it instantly |
| 5 | **Platforms** | Telegram + Web + WhatsApp — zero install friction |
| 6 | **Features** | Clips, full downloads, file conversion, queue, scheduling, prophecy bank |
| 7 | **Architecture** | Flask dashboard + Python bot + SQLite → lightweight, deploy anywhere |
| 8 | **Traction** | Live deployment with active subscribers, admin tools proven |
| 9 | **Business Model** | Freemium (free for single church) / White-label for ministries / Annual license |
| 10 | **Ask** | Beta partners, investment for WhatsApp API + iOS integration |

---

## Audience Angles

### For Investors

> ShareStill is the Shopify of church content distribution. Every church in the world produces content they need to distribute — and currently has no good way to do it. The global church software market is estimated at $5B+. ShareStill is a single-binary deploy that replaces email newsletters, custom apps, and social media posting with one click. We're starting with Telegram (high-engagement, low-friction) and expanding to WhatsApp Business API and iOS. Unit economics: $0 marginal cost per subscriber. Revenue model: annual license per church ($500–$2000 depending on size) + white-label ($5000+).

**Key metric pitch:** A church of 200 members currently spends $200/month on email tools + $100/month on social ads + $3000/year on a part-time social media person. ShareStill replaces all of it for <$500/year.

### For Churches & Ministries

> Stop fighting the algorithm. If your sermons, prophecies, and testimonies are getting buried on Instagram and Facebook, ShareStill gives you a direct line to your people. Your members subscribe once — through Telegram or your website — and every new message lands directly in their phone. Text, audio, video — all in one place. No app store. No login. No spam folder. It's like a private podcast feed for your church, delivered to their chat.

**Objection handling:**
- *"We already have a YouTube channel"* — YouTube requires people to navigate there. ShareStill brings content to where they already are (Telegram/WhatsApp).
- *"Our members are older, they don't use apps"* — Telegram is as simple as SMS. Once set up, they click one button to get content forever.
- *"We post on WhatsApp group"* — Groups get noisy, messages get lost. ShareStill delivers a dedicated, searchable feed.

### For General Users

> Tired of scrolling past your church's posts? Subscribe to ShareStill and get every sermon, prophecy, and testimony delivered straight to your phone. No scrolling. No algorithms. No noise. Just the content you actually want — in audio, video, or text. One tap to subscribe. Forever free.

**Also works for:** Anyone who follows a content creator and wants push delivery instead of pull (e.g., daily devotionals, teaching series, conference recordings).

---

## Competitive Landscape

| Product | Our Edge |
|---------|----------|
| Mailchimp / ConvertKit | Email has 20% open rates. Telegram has 90%+ delivery. |
| YouTube / Instagram | Algorithm controls who sees your content. ShareStill goes to everyone. |
| Custom mobile apps | $10k+ to build, nobody downloads. ShareStill uses Telegram (already installed). |
| WhatsApp Groups | Noisy, no structure, content gets buried. ShareStill is a clean feed. |
| Patreon / Substack | Takes a cut. Assumes monetization. ShareStill is for free distribution. |

---

## Technical Differentiators

- **One binary, zero infra:** Flask + SQLite + single bot process. Runs on a $5 VPS.
- **Content-agnostic pipeline:** yt-dlp integration means any URL format works — YouTube, Instagram, Google Drive, Vimeo, SoundCloud, 1000+ more.
- **Telegram as CDN:** Audio/video files stored on Telegram's servers (file_ids). No S3 bills.
- **Selective broadcast:** Send prophetic content to specific people, not everyone.
- **Prophecy Bank:** Personal user vault with favorites, tags, and search — turns passive consumption into an active library.

---

## Ask

- **Beta partners:** 3–5 churches willing to test and give feedback in exchange for free lifetime access
- **Technical investment:** WhatsApp Business API integration ($~200/mo) + potential iOS shortcut
- **Design:** Brand identity package (logo, colors, typography beyond the current lime/black)

---

*Built on paperlinkos.site · sharestill.paperlinkos.site*
