# CompetenceMatch design system (Task 8)

Status: implemented in `app/frontend` (tokens: `src/lib/tokens.css`, primitives: `src/components/ui/*`,
shell: `src/components/AppShell.tsx`, routes: `src/routes.tsx`). Light theme only; dark mode deferred.

Process: `ui-ux-pro-max` skill, `--design-system` query "job matching career platform SaaS dashboard clean blue"
(density 6, motion 3). Its output (indigo palette, flat style, Inter) was adapted to the user's reference
mockups: blue/white product UI, teal accent, rounded cards with soft shadows, numbered step sidebar.

## 1. Audit of the pre-Task-8 UI

| # | Problem | Fix |
|---|---|---|
| 1 | No app shell or routing: a stage state machine, no URLs, no back button, no deep links | `react-router-dom` routes, guarded layout, resume-on-boot |
| 2 | Each screen built its own header/logout; welcome/profile had no shell at all | One `AppShell` with sidebar stepper, top bar, step strip |
| 3 | Raw palette classes (`slate-*`, `blue-*`, `emerald-*`, `#1c1c1c`) scattered across screens | Semantic tokens only (`ink`, `primary`, `success-soft`...) |
| 4 | Single amber `Alert` used for errors, notes and warnings (colour meaning wrong) | `Alert` variants `danger/warning/info/success`, each with an icon |
| 5 | Buttons/tabs 32-40 px high | 44 px minimum touch targets (`min-h-11`) |
| 6 | Auth: no inline validation, no show/hide password, centred card only | Split layout, field-level errors with `aria-invalid`/`aria-describedby`, password toggle |
| 7 | Results tabs: no arrow-key support | `Tabs` primitive with roving tabindex (WAI-ARIA tabs) |
| 8 | Vacancy card showed a black "d" badge and "Джерело: Djinni" for synthetic fixtures (data-honesty violation) | Neutral company mark; source note "вакансії синтетичні" in sidebar, auth panel, results note |
| 9 | Invalid list markup (`<ul>` with `<div>` children around `<li>` ScoreBar) | `ScoreBar` renders a `div`; callers wrap in `li` |
| 10 | System font only; Cyrillic rendering varies per OS | Inter Variable (self-hosted via `@fontsource-variable/inter`, includes Cyrillic subsets) |
| 11 | No skip link, no focus move on navigation, English `<title>` | Skip link, focus to page `h1` on route change, Ukrainian titles |
| 12 | Loading text only, no skeletons; generic empty states | `Skeleton`, `EmptyState` |

## 2. Tokens (`src/lib/tokens.css`, Tailwind v4 `@theme`)

Colour (all text pairs checked, WCAG AA):

| Token | Value | Use | Contrast |
|---|---|---|---|
| `primary` / `primary-hover` / `primary-strong` | `#2563eb` / `#1d4ed8` / `#1d4ed8` | CTAs, active step, links | white on primary 5.17:1 |
| `primary-soft` / `primary-line` | `#eff4ff` / `#c7d7fe` | active pill, chips, borders | primary-strong on soft 6.08:1 |
| `accent` / `accent-ink` / `accent-soft` | `#0d9488` / `#0f766e` / `#e6f6f4` | heading rule, completed steps, decorative | accent-ink on soft 4.91:1 |
| `brand-deep` | `#1e3a8a` | gradients | |
| `canvas` / `surface` / `surface-muted` | `#f3f6fb` / `#fff` / `#f1f4f9` | page / cards / wells | |
| `ink` / `ink-muted` / `ink-subtle` | `#0f172a` / `#475569` / `#5a677d` | body / secondary / meta text | subtle on canvas 5.28:1 |
| `line` / `line-strong` | `#e3e8f0` / `#cbd5e1` | borders, input borders | |
| `success`, `warning`, `danger`, `info` (+ `-ink`, `-soft`) | emerald / amber / red / blue | status; text always uses `*-ink` on `*-soft` | 4.7-7.3:1 |

Typography: `Inter Variable` -> system-ui fallback. Scale: 12 (meta) / 14 (UI) / 16 (body, inputs on mobile to avoid iOS zoom) /
18 (card title) / 20-24 (section) / 30-44 (hero, extrabold, tight tracking). Line-height 1.5 body, 1.15 headings.

Spacing: Tailwind 4 px scale; card padding 20/24 px, page gutter 16/24/32 px, section gap 16-24 px.
Radius: 12 px controls (`rounded-xl`), 16 px cards (`rounded-2xl`), 24 px hero (`rounded-3xl`), full for pills/avatars.
Shadows: `shadow-card` (resting), `shadow-raised` (menus, dialogs, auth card), `shadow-float` (illustration), `shadow-nav` (bottom bar) — all blue-tinted and low opacity.
Motion: 150 ms colour transitions, 240-300 ms enter (`fade-up`, `msg-in`), easing `cubic-bezier(.2,0,0,1)`; global `prefers-reduced-motion` override disables animation and transitions.
Breakpoints: Tailwind defaults; `lg` (1024) switches bottom tab bar <-> sidebar; `xl` (1280) enables the two-column hero. Supported 320-1440 px without horizontal scroll.

## 3. Component patterns

- **Shell**: sidebar = numbered vertical stepper (Вітання, Профіль, Інтерв’ю, Результати, Вакансії, Профіль ринку). States: current (blue pill), done (teal check), available, locked (`aria-disabled`, lock icon, reason in `title` and screen-reader text). Availability is a pure function (`stepStates`) of the candidate stage: nothing past the profile opens before the interview (no job choice before the interview), results/vacancies/market open only after it. Top bar: hamburger (collapses sidebar on desktop, opens drawer `<dialog>` on mobile), product title, user menu (Профілі, Вийти). Step strip with `h1` "Крок N із 6: …" and a progress bar.
- **Mobile**: bottom tab bar with 5 steps (profile step via drawer), safe-area padding, hidden in the interview focus layout to give the chat room.
- **Forms**: `Field` = label + control + hint + inline error (icon + text); validate on blur and submit, focus first invalid field; server errors in a `danger` Alert.
- **Cards/lists**: white card, 1 px `line` border, `shadow-card`; list rows as bordered cards with avatar/icon mark, title, meta, badges, right-side metric.
- **States**: loading = skeletons + `role="status"` text; empty/locked/404 = `EmptyState` (icon, title, one sentence, one action); errors = `Alert role="alert" variant="danger"` close to the action.
- **Dialogs**: native `<dialog>` (`showModal`) for focus trap and Esc; labelled by its heading; backdrop click closes.
- **Dashboards/data**: numbers in `tabular-nums`; bars always paired with a text band or value (no colour-only meaning).

## 4. Key decisions

1. Blue primary over the skill's indigo: matches the reference mockups and gives 5.2:1 with white text.
2. Teal accent is reserved for "done/positive" signals and decoration so status colour stays unambiguous.
3. The step strip owns the page `h1`; page hero titles are `h2` styled large. One `h1` per page keeps route-change focus predictable.
4. Locked steps stay visible and focusable (`aria-disabled`) so users learn the journey and why a step is closed.
5. The welcome illustration is static, `aria-hidden` decoration; its percentages are illustrative "збіг профілю" values, never a hiring probability.
6. No notification bell from the mockup: there is no notification feature, and a dead control would violate "working actions".
