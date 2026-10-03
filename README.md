<p align="center">
  <img src="docs/readme/banner.svg" alt="Talk with Reachy Math: spoken math games for kids aged 10 to 13 on Reachy Mini" width="100%">
</p>

<p align="center">
  <a href="#what-a-game-sounds-like">A game</a> ·
  <a href="#what-the-app-does">What it does</a> ·
  <a href="#how-reachy-checks-an-answer">How answers are checked</a> ·
  <a href="#math-topics-and-levels">Topics and levels</a> ·
  <a href="#what-gets-recorded">What gets recorded</a> ·
  <a href="#try-it">Try it</a> ·
  <a href="STUDY_SETUP.md">Study setup guide</a>
</p>

**Talk with Reachy Math** is an app for [Reachy Mini](https://github.com/pollen-robotics/reachy_mini), a small robot by Pollen Robotics. Reachy plays short spoken math games with children aged about 10 to 13 (US grades 5 to 7), in English. It reads each problem aloud, listens to the child's answer, and, when the answer is not right yet, helps with small step-by-step questions. Every answer is checked in code, not by the language model, so Reachy never calls a wrong answer right.

The app is built on **[Talk with Reachy](https://github.com/renkaima/talk_with_reachy)**, so it also keeps a research record of each conversation: what was said, when it was said, and who said it, recognized by voice. It was built for research studies.

## What a game sounds like

An example; Reachy's exact wording varies.

> **Reachy:** Hi! I'm Reachy, a little robot who loves math games. Want to play a quick one with me?<br>
> **Child:** Sure!<br>
> **Reachy:** What is 75 times 9?<br>
> **Child:** Probably around seven hundred?<br>
> **Reachy:** Great estimate, that's really close! Let's break 75 into 70 and 5. What is 70 times 9?<br>
> **Child:** 630.<br>
> **Reachy:** Yes! Now, what is 5 times 9?<br>
> **Child:** 45.<br>
> **Reachy:** Last step: what is 630 plus 45?<br>
> **Child:** 675!<br>
> **Reachy:** You worked it out step by step: 75 times 9 is 675. Want another one?

## What the app does

**For the child**

- Reachy opens by asking whether they want to play a quick math game. If they say no, Reachy just chats and asks again a few minutes later.
- Reachy talks like a friendly coach for a 10-year-old: short sentences, everyday words, and praise for effort. It never says "wrong"; it says "Not quite yet".
- When an answer is not right, or the child says "I don't know", Reachy breaks the problem into small helper questions instead of giving the answer.
- Problems get harder or easier as the child goes, separately for each topic and each child.

**For the researcher**

- Every problem, answer, helper question, and level change is logged with its time and the child's speaker ID.
- Each child's level is kept between sessions, found by their voice.
- Everything Talk with Reachy records is recorded too: timed transcripts, speaker IDs by voice, an audio clip per person utterance, and robot actions. The robot uploads it all to a Google Drive folder every five minutes.

## How Reachy checks an answer

<p align="center">
  <img src="docs/readme/math_turn.svg" alt="Diagram: the child's answer goes through speech recognition to the language model, which passes the child's exact words to the math coach in the app. The coach reads the number, compares it with the answer worked out when the problem was made, decides what Reachy says next, and records the child's level. The language model then says what the coach decided." width="100%">
</p>

1. **Reachy reads a problem** that the app generated, with its answer already worked out. Word problems come from a set of 300 [GSM8K](https://github.com/openai/grade-school-math) problems chosen for this age group.
2. **The child answers aloud.** The speech service turns the answer into text, and the language model passes the child's exact words to the app's math coach.
3. **The math coach reads the number** from those words: digits, number words ("seventy-two"), decimals, fractions ("three fourths"), mixed numbers, and negatives.
4. **The coach compares it with the stored answer and decides what comes next.** A right answer gets praise. An answer that is not right yet gets a small helper question, and a guess within 10 percent is praised as a good estimate. After the last helper question, Reachy says the whole answer, and explains it if the child's last answer was not right either.
5. **The coach records the result.** It writes every answer to the study log and, when a problem is finished, updates the child's level for that topic. The language model then says what the coach decided, in a child's words.

## Math topics and levels

Eight topics follow the US Common Core standards for grades 5 to 7, and a ninth gives word problems. Each topic has three levels. Practice stays on one topic for five problems and then moves to the next, unless the child asks for a topic.

| Topic | Level 1 | Level 2 | Level 3 | How Reachy helps |
|---|---|---|---|---|
| Multiplication | 2-digit × 1-digit | 2-digit × 2-digit | 3-digit × 2-digit | breaks a number into tens and ones |
| Division | 2–3 digits ÷ 1 digit | 3 digits ÷ 2 digits | 3–4 digits ÷ 2 digits | takes away a round number of groups first |
| Fractions | add, same bottom number | add or subtract, different bottom numbers | fraction of a number; fraction × fraction | makes the bottom numbers the same |
| Decimals | add or subtract tenths | add or subtract hundredths | multiply | thinks of the numbers as money |
| Percentages | 10, 25, 50 percent | 5, 20, 30, 40, 60, 75 percent | 12, 15, 35, 45, 65, 85 percent | starts from 50, 25, or 10 percent |
| Negative numbers | add | subtract a negative | multiply | uses a number line and the sign rules |
| Order of operations | a + b × c | (a + b) × c − d | a × b − c ÷ d | does one operation at a time |
| Equations | x ± a = b | a × x = b | a × x + b = c | treats x as a mystery number |
| Word problems | 2 steps | 3 steps | 4 steps | asks one calculation of the solution at a time |

**How levels change.** Each child starts every topic at level 1. Three problems in a row answered right on the first try move the child up one level. Two problems in a row in which Reachy had to give away an answer move the child down one level. A problem solved with help, with every helper question answered right, leaves the level as it is.

## A study session, step by step

| When | Who | What happens |
|---|---|---|
| **Before** | Researcher | Installs the app on the robot from the Reachy Mini Control app, signs the robot in to Google Drive once, and enrolls each child's voice (about 20 seconds of speech per child). |
| **During** | Children | Reachy invites them to a math game, plays a few problems with each child at that child's level, and chats in between. |
| **After** | Researcher | Opens the Google Drive folder *Talk with Reachy Math*. It holds the transcripts with all math events, the audio clips, and each child's math progress. The same files stay on the robot. |

## How the recording works

<p align="center">
  <img src="docs/readme/how_it_works.svg" alt="Diagram: the microphone audio goes to a speech service that turns speech into text, writes a reply with a language model, and speaks it through Reachy. On the device, the app also keeps a copy of the audio, identifies the speaker by voice, writes one record per utterance, and uploads the data folder to Google Drive every five minutes. Voice ID also sends the language model a hidden note saying who is speaking." width="100%">
</p>

- **Voice ID runs on the device.** The app cuts each person utterance out of a copy of the microphone audio and computes a voiceprint with NVIDIA's TitaNet-S speaker model, run locally with [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). The best-matching known voice gives the speaker ID, which also tells the math coach whose level to use.
- **Reachy is told who is speaking** through a note that is not spoken aloud, with the person's name and what Reachy remembered about them.
- **The study recorder** writes one record per utterance (words, start and end times, speaker ID, audio clip) and every math event into the data folder, and **the uploader** copies the folder to Google Drive every five minutes.

[Talk with Reachy's README](https://github.com/renkaima/talk_with_reachy#how-it-works) explains these parts in more detail.

## What gets recorded

Everything goes into one data folder, `~/talk_with_reachy_math_data/` on the robot (or on the Mac, in the simulation):

```
talk_with_reachy_math_data/
├── transcripts/<robot>_<date-time>_<id>.jsonl   one file per app run, with all math events
├── transcripts/<same name>.csv                  the same timeline as a spreadsheet
├── audio/<same name>/<seq>_<speaker ID>.wav     one clip per person utterance
├── people/library.json                          voiceprints of all known voices
├── people/<speaker ID>/memory.v1.json           what Reachy remembers about each child
└── people/<speaker ID>/math_progress.json       the child's level in each topic
```

The math events are `math_problem` (the problem, its topic and level, and the answer), `math_answer` (what the child said, the number read from it, whether it was right, and which helper question it answered), `math_level_change`, and `math_practice_stopped`. One answer looks like this (one line in the file, spread out here):

```json
{
  "session_id": "9f2c…",
  "type": "event",
  "event": "math_answer",
  "time": "2026-10-03 10:15:42.118-04:00",
  "elapsed_s": 41.307,
  "problem_id": "M001",
  "answered_by": "P01",
  "asked_to": "P01",
  "heard": "Probably around seven hundred?",
  "parsed": "700",
  "step": null,
  "seconds_since_asked": 6.2,
  "attempt": 1,
  "close": true,
  "correct": false
}
```

[STUDY_SETUP.md](STUDY_SETUP.md#math-practice) describes every field and event.

## Try it

**In the simulation, without a robot.** Start the simulation in the Reachy Mini Control app on a Mac, install Talk with Reachy Math, and talk through the Mac's microphone. The app writes transcripts, speaker IDs, audio clips, and math events to `~/talk_with_reachy_math_data` on the Mac. To test the Google Drive upload as well, sign the Mac in once with `bash deploy/google_dry_run.sh` ([details](STUDY_SETUP.md#5-sign-in-to-google-drive-one-time-per-device)).

**On a Reachy Mini.** The installable app is a private Hugging Face Space, because it carries the app's Google sign-in secret. To get access, contact [@renkaima](https://github.com/renkaima). The app then appears in the Control app's store under *Private*. [STUDY_SETUP.md](STUDY_SETUP.md#setup-in-order) lists every setup step, from publishing the Space to enrolling children.

**From source, for developers.** The [developer reference](docs/ORIGINAL_README.md) covers installing from source, configuration, and command-line options; here the command is `talk-with-reachy-math`. The Google client secret is not in this repository, so a copy run from source keeps its study files on the device.

## Good to know

- **A misheard number is checked as heard.** The coach checks what the speech service transcribed. The audio clip of each answer is saved, so answers can be checked by ear.
- **The language model decides when to call the math coach.** If it ever answers by itself instead, no `math_answer` event is logged for that problem; the transcript still shows what was said.
- **Audio leaves the device.** As in Pollen's app, the microphone audio goes to the speech service on Hugging Face, and the hidden notes send it names and what Reachy remembers about each person. To keep audio on your own hardware, run your own speech service ([connection modes](docs/ORIGINAL_README.md#hugging-face-connection-modes)).
- **Check voice ID before relying on it,** especially with children's voices: the voice-matching thresholds come from a check on clean recordings of six speakers and have not been validated on children's voices or in a noisy room ([details](STUDY_SETUP.md#voice-identification)).
- **Separate from Talk with Reachy.** This app has its own data folder, Google Drive folder, Google sign-in, and voice library, and its Python package `talk_with_reachy_math` installs next to the other apps on the same robot.
- **Math can be switched off** with the setting `TALK_WITH_REACHY_MATH_PRACTICE=0`.

## Credits and license

- Built on [Talk with Reachy](https://github.com/renkaima/talk_with_reachy), which is built on Pollen Robotics' [reachy_mini_conversation_app](https://github.com/pollen-robotics/reachy_mini_conversation_app) (both Apache 2.0). The changes from Talk with Reachy are the commits after commit `624b78b`, and the changes from Pollen's app are the commits after upstream commit `5eb39ed`. This app is not affiliated with or endorsed by Pollen Robotics; "Reachy Mini" names the robot that the app runs on.
- Word problems: a subset of [GSM8K](https://github.com/openai/grade-school-math) by OpenAI (MIT License; see `src/talk_with_reachy_math/math_data/GSM8K_LICENSE.txt`).
- Voice ID uses NVIDIA NeMo's TitaNet-S speaker model through [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx).
- Maintained by Renkai Ma ([@renkaima](https://github.com/renkaima)).
- License: Apache 2.0, see [LICENSE](LICENSE).
