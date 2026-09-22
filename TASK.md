# Task: Build "Catch The Train", a Commute Helper Bot

## Background
Many Bay Area commuters drive from home to a BART station, park, take the train to
work, and do the reverse in the evening. Each day they have the same questions:
*"When do I need to leave home to catch a train?"* and *"When do I leave the office
so I'm not stuck on the platform for 20 minutes?"*

Build a **Telegram bot** that answers those questions and sends reminders when it's
time to leave.

This is a learning project. The requirements say **what** to build, not **how**.
Some parts are left vague on purpose (see [Open Questions](#open-questions)). When
you hit one, make a decision, write it down, and keep going.

---

## Goals
- A working Telegram bot that anyone can message and set up for their own commute.
- Leave-by times based on **real BART train data**, not guesses.
- Reminders sent on commute days without the user having to ask.
- Runs unattended on a small machine (a Raspberry Pi, a cheap cloud VM, or your laptop).

## Non-Goals
- Transit systems other than BART.
- Live traffic data. Drive times are whatever the user tells you.
- A web or mobile app. The only interface is Telegram.

---

## Functional Requirements

### 1. Onboarding / Setup
- A new user starts the bot and is taken through a conversational setup.
- Setup must collect at least:
  - One or more **home stations** (stations the user can drive to and park at).
  - An **office station**.
  - **Drive time** from home to each home station.
  - **Walk times**: parking lot → platform, and platform → office.
  - **Commute days** (e.g. Tuesdays and Thursdays only, or every weekday).
  - **Morning and evening alert windows**, the time ranges when the user wants reminders.
- Users should be able to enter stations the way people naturally would: by name,
  by abbreviation, and with small mistakes or typos.
- Users should be able to cancel setup partway through, and redo it later.
- Invalid answers should get a helpful reply, not a crash or silence.

### 2. Viewing and Editing Settings
- A user can see a summary of their current settings.
- A user can change **one** setting without redoing the whole setup.
- A user can delete all of their data.

### 3. Trip Planning: To the Office
- The user can ask "when should I leave home?" and get:
  - the **next** good option, or
  - **several** upcoming options to choose from.
- The user can also give a target arrival time ("I need to be at the office by 9:45").
- Each option should tell the user at least: when to leave home, which station to
  drive to, which train to catch, and roughly when they'll get to the office.
- If the user has several home stations, compare them and show only the options
  that are actually worth considering.

### 4. Trip Planning: To Home
- The user can ask "when should I leave the office?" for the next train(s), or for a
  specific departure time.
- The trip home should end at the station **where the car is actually parked**, which
  may not be the user's "usual" station.
- Show an estimated time of arriving home.

### 5. Car Location
- The bot needs to know which station the car is parked at.
- The user can set this manually.
- The bot should also be able to work it out from how the user commuted that morning.

### 6. Time-to-Leave Alerts
- On commute days, within the user's alert windows, the bot sends a message a few
  minutes before the user needs to leave.
- Alerts need quick actions: one for "I'm leaving now" and one for "not going today".
  Either one stops further alerts in that direction for the rest of the day.
- If the user ignores an alert and misses that train, they should be reminded about
  the next one.
- Users can switch alerts off and on.
- The bot must never send the same alert twice.

### 7. Multi-User
- Many people can use the same bot, each with their own settings and alerts.
- The operator can cap how many users can sign up.
- If a user blocks the bot, handle it cleanly.

---

## Non-Functional Requirements
- **Language**: your choice. (The reference version uses Python.)
- **Persistence**: settings and today's alert progress must survive a restart.
- **Deployment**: must run on a machine **with no public IP or open inbound ports**.
- **Configuration**: secrets (bot token, API keys) come from the environment, never
  from the code.
- **Cost / efficiency**: don't call the BART API more often than you need to. Think
  about what happens with 50 users and a check every minute.
- **Time zones**: BART runs on Pacific time. Your server might not.
- **Testing**: the planning math and input parsing need automated tests. You should
  be able to run the tests without Telegram or network access.
- **Docs**: a README explaining how to set up, run, and deploy the bot.

---

## External Services
- **Telegram Bot API**: create a bot through @BotFather.
- **BART Legacy API** (api.bart.gov): provides schedules, real-time departures, and
  station data. There is a public demo key, and you can register your own.

Reading and understanding these APIs is part of the task.

---

## Open Questions
These are deliberately left unanswered. For each one, pick an approach, and write
down what you chose and why (in the README, or a `DECISIONS.md`).

1. **What does "leave-by time" mean exactly?** What goes into it: drive, walk, some
   slack for parking and fare gates? Should the user be able to adjust the slack?
2. **Scheduled vs. real-time data.** BART publishes a timetable and also live
   departure estimates. Which do you use, when, and what happens when they disagree?
3. **"Options worth considering."** If two home stations both get you to work, when
   should you hide one of them?
4. **Alert timing.** How long before the leave time should an alert go out? Is that
   fixed or set by the user? What if the bot was down and starts up partway through
   a window?
5. **Time input formats.** Users will type `9:45`, `9.45`, `945`, `9:45am`, `5-6:30`,
   `5pm to 6:30`… Which ones do you accept? Is `5-6:30` in the *evening* window
   AM or PM?
6. **Alert window limits.** Can a window go past midnight? Is 12 hours too long?
7. **What counts as "today"?** When does alert progress reset?
8. **Fuzzy station matching.** How close does a typo have to be to count as a match?
   What do you do when the input could mean more than one station?
9. **Failure modes.** What does the user see if BART's API is down, slow, or returns
   nothing (late at night, holidays, service changes)?
10. **Privacy.** What exactly does "delete my data" remove? What do you keep, if
    anything?
11. **Limits.** How many home stations can a user have? What happens to the
    user who would go over the sign-up cap?

---

## Milestones (suggested)
1. **CLI prototype**: hard-code one commute, call BART, print leave-by times.
2. **Planning logic + tests**: both directions and multiple home stations, with unit tests.
3. **Basic bot**: planning commands work in Telegram for a single hard-coded user.
4. **Setup and storage**: conversational setup, saved settings, multiple users.
5. **Alerts**: the scheduled job, action buttons, no duplicate alerts.
6. **Polish**: typo handling, settings editing, error messages, deployment.

## Done When
- A new person can message the bot, finish setup in a couple of minutes, and get
  correct leave-by times.
- They get timely, non-duplicated alerts on their commute days, and the alerts stop
  when they tap a button.
- The bot keeps running through restarts and brief network outages.
- Tests pass, and the README is enough for someone else to deploy it.

## Stretch Ideas
- Warn about delays or service advisories.
- Let a user pause alerts for a holiday or vacation.
- Weekly summary: how often they caught the train they were alerted for.
- Support people who walk or bike to the station instead of driving.
