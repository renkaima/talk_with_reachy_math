# Talk with Reachy Math: study setup

This app is [Talk with Reachy](https://github.com/renkaima/talk_with_reachy) plus math practice. Talk with Reachy is a fork of Pollen Robotics' [Reachy Mini conversation app](https://github.com/pollen-robotics/reachy_mini_conversation_app). Compared with the official app, this one adds study data collection, changes one conversational behavior, and adds math practice:

1. **Timed transcripts.** Every finished utterance, by a person or by Reachy, is logged with its start time, end time, and duration. Each app run produces a JSONL file and a CSV copy of the same timeline.
2. **Voice identification.** Each person utterance is matched against known voices and labeled with a speaker ID such as `P01` (a participant a researcher enrolled) or `V003` (a voice the app learned on its own).
3. **Audio clips.** The audio of each person utterance is saved as a WAV file, so that a researcher can check by ear who spoke.
4. **Event log.** Robot actions (dances, emotions, camera use), people talking over Reachy, connection and upload problems, and clock synchronization are logged on the same timeline.
5. **Per-person memory.** Reachy is told who is speaking and keeps separate memories for each person. In the official app, one memory list is shared by everyone. This is the behavior change.
6. **Google Drive upload.** The robot copies all of the above directly to a folder in Google Drive every five minutes. No computer needs to be nearby; the robot only needs internet access.
7. **Math practice.** After about two minutes of conversation, Reachy offers short spoken math practice for children aged about 10 to 13. Problems are generated and checked in code, each child's level is kept per speaker ID, and every problem and answer is logged (see [Math practice](#math-practice)).

UC's Office of Information Security declined the OneDrive integration on 2026-10-01. The OneDrive code is still in the repository but is switched off (`CLIENT_ID` in `onedrive_upload.py` is empty).

The Python package is named `talk_with_reachy_math` because Reachy Mini installs all apps into one shared environment. With another app's name, installing this app would replace that app; with its own name, it installs next to Talk with Reachy and the official conversation app.

Talk with Reachy Math keeps its data apart from Talk with Reachy. It has its own data folder (`~/talk_with_reachy_math_data`), its own Google Drive folder (**My Drive → Talk with Reachy Math**), its own Google sign-in on the robot, and its own voice library, so participants enrolled in Talk with Reachy have to be enrolled again here. Its commands start with `talk-with-reachy-math` and its settings with `TALK_WITH_REACHY_MATH_`.

## What is recorded

Everything is stored in one data folder: `/home/pollen/talk_with_reachy_math_data/` on the robot, or `~/talk_with_reachy_math_data/` on a Mac running the simulation.

```
talk_with_reachy_math_data/
├── transcripts/<robot>_<YYYYMMDD-HHMMSS>_<id>.jsonl   one file per app run
├── transcripts/<same name>.csv                         the same timeline as a spreadsheet
├── audio/<same name>/<seq>_<speaker ID>.wav            one clip per person utterance
├── people/library.json                                 voiceprints of all known voices
├── people/<speaker ID>/memory.v1.json                  what Reachy remembers about that person
├── people/requests_log.jsonl                           every voice command and its result
└── models/nemo_en_titanet_small.onnx                   the speaker model (not uploaded)
```

### Transcript records

Each line of the JSONL file is one record. The first record is `session_start` and the last is `session_end`. In between are `utterance` and `event` records, in the order in which they happened. When the app stops normally, one `speaker_summary` record per speaker comes just before `session_end`:

```json
{"session_id": "9f2c…", "type": "session_start", "time": "2026-10-01 09:00:12.345-04:00", "elapsed_s": 0.0, "schema_version": 3, "robot_id": "reachy-mini", "app_version": "1.2.0", "utc_offset": "-0400", "clock_synced": true, "voice_id": {"enabled": true, "model": "nemo_en_titanet_small.onnx", "match_threshold": 0.45}}
{"session_id": "9f2c…", "type": "utterance", "seq": 1, "time": "2026-10-01 09:00:16.020-04:00", "start": "2026-10-01 09:00:13.101-04:00", "end": "2026-10-01 09:00:15.870-04:00", "duration_s": 2.769, "elapsed_s": 0.756, "speaker": "person", "speaker_id": "P01", "speaker_name": "Alice", "match_score": 0.712, "id_status": "matched", "audio_file": "audio/reachy-mini_20261001-090012_9f2c12/0001_P01.wav", "text": "Hi Reachy, what are you doing?"}
{"session_id": "9f2c…", "type": "event", "event": "tool_started", "time": "2026-10-01 09:00:16.900-04:00", "elapsed_s": 4.555, "tool": "dance", "args": "{\"move\": \"happy\"}", "idle": false, "call_id": "call_8"}
{"session_id": "9f2c…", "type": "utterance", "seq": 2, "time": "2026-10-01 09:00:19.410-04:00", "start": "2026-10-01 09:00:16.430-04:00", "end": "2026-10-01 09:00:19.300-04:00", "duration_s": 2.87, "elapsed_s": 4.085, "speaker": "reachy", "speaker_id": "reachy", "speaker_name": "Reachy", "text": "Just looking around! Want to see a dance?"}
{"session_id": "9f2c…", "type": "speaker_summary", "time": "2026-10-01 11:45:03.001-04:00", "elapsed_s": 9890.656, "speaker_id": "P01", "speaker": "person", "speaker_name": "Alice", "utterances": 1, "speech_s": 2.769}
{"session_id": "9f2c…", "type": "speaker_summary", "time": "2026-10-01 11:45:03.001-04:00", "elapsed_s": 9890.656, "speaker_id": "reachy", "speaker": "reachy", "speaker_name": "Reachy", "utterances": 1, "speech_s": 2.87}
{"session_id": "9f2c…", "type": "session_end", "time": "2026-10-01 11:45:03.002-04:00", "elapsed_s": 9890.657, "utterances": 2}
```

Utterance fields:

| Field | Meaning |
|---|---|
| `seq` | Order of the utterance within the run. It also numbers the audio clip. |
| `start`, `end` | When the utterance began and ended, as local time with milliseconds and UTC offset. |
| `duration_s` | `end` minus `start`, in seconds. |
| `elapsed_s` | Seconds from app start to the start of the utterance. This value comes from a clock that never jumps, so it stays correct even when the robot's wall clock is wrong (see [Clock](#clock)). |
| `speaker` | `person` or `reachy`. |
| `speaker_id` | `reachy`, an enrolled ID such as `P01`, an automatic label such as `V003`, or `unknown`. |
| `speaker_name` | The name entered for this voice when it was enrolled, renamed, or linked (`Reachy` for Reachy). Empty for voices without a name, such as new automatic voices. A later rename does not change names already logged. |
| `match_score` | Cosine similarity between this utterance's voiceprint and the closest known voice, from -1 to 1. Higher means more similar. For a new voice, it is the score of the closest *other* voice, which is why it is low. |
| `id_status` | How the speaker ID was decided; see [Voice identification](#voice-identification). |
| `overlaps_reachy` | `true` when the person started talking while Reachy was still speaking. |
| `interrupted` | On a Reachy utterance: `true` when a person talked over it. Its `end` is then the moment the person started. |
| `audio_file` | The utterance's audio clip, relative to the data folder. |
| `text` | What was said, as transcribed by the speech server. |

Speaker summary fields (one record per `speaker_id`, in order of each speaker's first utterance):

| Field | Meaning |
|---|---|
| `speaker_id`, `speaker`, `speaker_name` | As in utterances. `speaker_name` is the latest name logged for that ID in the run. All unidentified utterances share the ID `unknown`. |
| `utterances` | Number of utterances by this speaker in the run. |
| `speech_s` | Sum of their utterances' `duration_s`, in seconds. |

The summary is written only when the app stops normally. If the robot loses power, it is missing, and the same numbers can be recomputed from the utterance records.

How the times are measured:

- **Person utterances.** The speech server reports where each turn starts and ends in the audio stream it received. The app keeps the last two minutes of the audio it sent, so it maps those positions back to the exact audio (saved as the clip) and to the time at which that audio was captured.
- **Reachy utterances.** `start` is when the first audio of a response arrived; playback starts immediately. `end` is `start` plus the length of the audio, or the moment a person started talking over it.

Only final transcripts are logged; partial, in-progress text is not. The person transcripts are what the speech server *heard*, not necessarily what was said. In our simulation test, "Hey Reachy" was transcribed as "Hey Rachel."

### The CSV timeline

The CSV file has one row per record and opens directly in Excel. Its columns are `seq`, `start`, `end`, `duration_s`, `elapsed` (as H:MM:SS.s), `kind` (`utterance`, `event`, or `summary`), `speaker`, `speaker_id`, `speaker_name`, `match_score`, `id_status`, `flags` (`interrupted`, `overlaps_reachy`), `text`, and `audio_file`. For events, `text` holds the event name and its details. For a `summary` row, `duration_s` is the speaker's total speech in seconds and `text` reads, for example, `12 utterances, 0:01:34.2 of speech`.

### Events

| Event | When it is logged |
|---|---|
| `tool_started`, `tool_finished` | Reachy runs a tool: a dance, an emotion, a head movement, the camera, `remember`, and so on. `idle: true` marks tools the app runs on its own after a long silence. `tool_finished` gives the outcome and duration. |
| `interruption` | A person starts talking while Reachy is speaking. |
| `speaker_note_sent` | Reachy is told who is speaking. The `note` field holds the exact text it received. |
| `new_voice` | Voice ID creates an automatic label for a voice it has not heard before. |
| `voice_enrollment_started`, `voice_enrolled`, `voice_enrollment_expired`, `voice_linked`, `voice_renamed`, `voice_deleted` | Voice commands take effect (see [Managing voices](#managing-voices)). |
| `voice_model_ready`, `voice_model_unavailable` | The speaker model has loaded, or cannot be loaded yet (it is retried every minute). |
| `backend_connected`, `backend_disconnected` | The connection to the speech server opens or closes, with the reason. |
| `mic_muted`, `mic_unmuted` | The microphone is muted or unmuted from the app's web page. |
| `upload_signed_out`, `upload_failing`, `upload_recovered` | Upload problems start or end (`target` says where: `Google Drive`). A failure that continues is logged once, not on every pass. |
| `clock_sync` | The robot's clock becomes synchronized (or stops being synchronized) with network time. |
| `math_offer_prompted`, `math_problem`, `math_answer`, `math_level_change`, `math_problem_skipped`, `math_practice_stopped` | Math practice; see [Math practice](#math-practice) for the fields. |

### Clock

The robot has no battery-backed clock. If it starts without internet, its wall clock can be wrong until it reaches a time server. The `session_start` record therefore says whether the clock was synchronized (`clock_synced`), and a `clock_sync` event marks any later change. Absolute times recorded while `clock_synced` was `false` may be wrong; `elapsed_s` and `duration_s` are always correct.

## Voice identification

For each person utterance of at least one second, the robot computes a voiceprint: 192 numbers produced by NVIDIA NeMo's TitaNet-S speaker model, which runs locally on the robot's processor through [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx). The voiceprint is compared with every voice in `people/library.json`:

| Situation | `speaker_id` | `id_status` |
|---|---|---|
| Score ≥ 0.45 against a known voice | that voice | `matched` |
| Score < 0.30 against every known voice, and at least 2 s of speech | a new automatic label (`V001`, `V002`, …) | `new_voice` |
| Anything in between | `unknown` | `uncertain` |
| Less than 1 s of speech | `unknown` | `too_short` |
| An enrollment is in progress and this is the enrolling person | the enrollment ID | `enrolling`, then `enrolled` |
| The speaker model has not loaded yet | `unknown` | `model_not_ready` |

There are two kinds of voices:

- **Enrolled voices** (`P01`, `R01`, …) are registered by a researcher (see below). Their voiceprint does not change afterwards.
- **Automatic voices** (`V001`, …) are created when an unfamiliar voice speaks long enough. Each confident later match refines the voiceprint slightly. A researcher can later give an automatic voice a participant ID with `link`.

The thresholds come from a check on clean recorded speech (three English and three Mandarin speakers). In that check, every clip of one second or more was attributed to the right speaker; clips scored at least 0.47 against their own speaker and at most 0.34 against others. **This has not been validated on the voices of the study population or in a noisy day room.** Before relying on the speaker IDs, run a pilot in which an observer writes down who is speaking, and compare those notes with the transcript. Because every clip is saved, all utterances can be scored again later with a different threshold (`TALK_WITH_REACHY_MATH_VOICE_MATCH_THRESHOLD`) or a different model.

Known limits:

- Each utterance gets one label. If two people speak in the same turn, the clip mixes their voices; it is labeled after whoever dominates it, or `unknown`.
- Reachy learns who is speaking one turn late. The speaker note reaches the model while it is already answering the current turn, so it applies from the next turn on.
- An automatic voice can split (one person gets two labels, for example on a bad day or with a cold) or merge (two similar voices share one label). `link` repairs a split; a merge needs re-enrollment.
- The first time the app starts, it downloads the 40 MB speaker model from the sherpa-onnx release page and checks its SHA-256 checksum. Utterances before the model is ready are labeled `model_not_ready`.

### Managing voices

The commands below change the voice library. Run them from the Mac, which connects to the robot over SSH (`reachy-mini.local` by default; prefix `ROBOT=<address>` to use another address, or `ROBOT=local` for the simulation on the Mac):

```bash
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh list
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh enroll P01 --name Mary
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh link V007 P02 --name Sam
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh link V009 V003
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh rename P01 "Mary J."
bash ~/ReachyMini/talk_with_reachy_math/deploy/voices.sh delete P01
```

On the robot itself, the same commands are `/venvs/apps_venv/bin/talk-with-reachy-math-voices <command>`.

- **`enroll P01 --name Mary`** registers a participant. After running it, let only that person talk with Reachy until they have spoken for about 20 seconds in total (`--seconds` changes this), which is usually one to two minutes of conversation. Speech from voices that are already enrolled (for example a researcher enrolled as `R01`) is recognized and skipped. Clips that disagree with the rest are left out of the voiceprint. An enrollment that is not completed within 15 minutes is cancelled. `--name` is the name Reachy may use for the person; leave it out if Reachy should not know their name.
- **`list`** shows every voice, its kind, name, number of utterances, when it was last heard, and its earlier labels.
- **`link V007 P02`** gives an automatic voice a participant ID. Transcripts written earlier keep `V007`; the library lists `V007` under the voice's earlier labels, so the two can be joined during analysis. Linking to an existing ID (`link V009 V003`) merges the two voices and their memories.
- **`rename P01 "Mary J."`** changes the name Reachy uses.
- **`delete P01`** removes the voiceprint and the memories on the robot, for example when a participant withdraws. It does not delete transcripts or audio clips that were already recorded, or the copies already in Google Drive. Delete those by hand: the person's clips have the ID in their file names, and the Drive folder `people/P01/` holds the last uploaded copy of their memories. The updated voice library replaces the old one in Drive on the next upload pass.

The running app applies each command within about two seconds. If the app is not running, the command waits and is applied at the next start. Every command and its result are appended to `people/requests_log.jsonl`.

## What Reachy knows about people

Whenever voice ID attributes an utterance to a different person than the previous one, the app adds a system note to the conversation, for example:

> Voice ID: the person speaking now is probably Mary (ID P01).
> What you remember about this person:
> - Likes gardening

The note is not spoken. The model uses it to address the person and to recall what it saved about them before. Each note is logged as a `speaker_note_sent` event with its full text.

The `remember` and `forget` tools now act on the current speaker's own memory file, `people/<speaker ID>/memory.v1.json`. If voice ID does not know who is speaking, nothing is saved. The shared memory list that the official app puts into every conversation is no longer used.

This changes the intervention compared with the official app: Reachy may greet people by name and bring up their earlier conversations, but it is instructed never to mention one person's memories to anyone else. Voice ID can be wrong, so this can still happen; the `speaker_note_sent` events show exactly what Reachy was told and when.

## Math practice

Reachy can run short spoken math practice for children aged about 10 to 13 (US grades 5 to 7). The conversation model only reads problems aloud and passes on what the child said. The problems, the answers, the checking, and the levels are all in code (`math_practice.py`), so Reachy never confirms a wrong answer as right.

The default profile (`profiles/default/profile.md`) makes Reachy a friendly robot coach that talks the way one would talk to a 10-year-old: one or two short sentences, everyday words, one small step at a time, and praise for effort. It never says "wrong" ("Not quite yet" instead), and it is told not to ask children for personal details such as a full name, address, or phone number.

### How a practice session goes

1. **Invitation.** Reachy opens the conversation by saying hi and asking whether the child wants to play a quick math game (the `greeting` in the default profile). If the child says no or talks about something else, the app later adds a system note, at the end of the next thing a person says, asking Reachy to invite the child again, by name if voice ID knows the child. The note comes at the earliest three minutes (`TALK_WITH_REACHY_MATH_OFFER_AFTER_S`) after the greeting, the previous note, or the end of practice, and never while practice is under way. Reachy drops the game if the child says no.
2. **Problem.** When the child agrees, Reachy calls `next_math_problem` and reads the problem it gets back.
3. **Answer.** Reachy calls `check_math_answer` with the child's exact words, both for answers to the problem and for answers to the helper questions below. The code reads the last number in them: digits, number words ("seventy-two"), decimals ("two point five"), fractions ("three fourths", "3/4", "three over four"), mixed numbers ("two and a half"), and negatives ("negative five"). Equivalent forms count as right (4 sixths for 2 thirds). For an answer such as 1 third, a decimal rounded to two or more places (0.33) also counts.
4. **Help in small steps.** A right first answer is praised. If the first answer is not right, or the child says they don't know or are stuck ("I don't know", "help", "it's too hard"), Reachy gives neither the answer nor a long hint. It says "Not quite yet" (or, when the answer is within 10 percent, that it was a great estimate) and asks the problem's first helper question, a smaller piece of the problem such as "Let's break 75 into 70 and 5. What is 70 times 9?". The code checks each helper answer too. A right one gets a short "Yes!" and the next helper question; a wrong one gets that helper's answer ("Almost! It's 630.") and the next helper question. If the child says the problem's answer at any point, the problem is solved. After the last helper question, Reachy says the whole answer; if the child's answer to that last question was not right either, Reachy also explains the answer in short sentences. If the child says something with no number and no request for help (for example, "um"), Reachy asks for the answer as a number; this does not count as a try.
5. **Stop.** Reachy calls `stop_math_practice` when the child wants to stop. Practice also counts as over after ten minutes without a problem or an answer.

### Topics and levels

Each topic has three levels. Without a request from the child, practice stays on one topic for five problems and then moves to the next one in this order:

| Topic | Standards | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|
| Multiplication | 5.NBT.5 | 2-digit × 1-digit | 2-digit × 2-digit | 3-digit × 2-digit |
| Division | 6.NS.2 | 2–3 digits ÷ 1 digit | 3 digits ÷ 2 digits | 3–4 digits ÷ 2 digits |
| Fractions | 5.NF.1, 5.NF.4 | add, same denominator | add or subtract, different denominators | fraction of a number, or fraction × fraction |
| Decimals | 5.NBT.7, 6.NS.3 | add or subtract tenths | add or subtract hundredths | multiply |
| Percentages | 6.RP.3c | 10, 25, 50 percent of a number | 5, 20, 30, 40, 60, 75 percent | 12, 15, 35, 45, 65, 85 percent |
| Negative numbers | 7.NS.1, 7.NS.2 | add | subtract a negative | multiply |
| Order of operations | 5.OA.1 | a + b × c | (a + b) × c − d | a × b − c ÷ d |
| Equations | 6.EE.7, 7.EE.4a | x + a = b or x − a = b | a·x = b | a·x + b = c |
| Word problems | GSM8K | 2 steps | 3 steps | 4 steps |

Helper questions follow one idea per topic: multiplication breaks a number into tens and ones; division first takes away a round number of groups ("4 times 80 is 320. What is 348 minus 320?"); fractions make the bottom numbers the same; decimals are thought of as money in cents; percentages start from 50, 25, or 10 percent; negative numbers use a number line, "taking away a negative is the same as adding", and the sign rule; order of operations does one operation at a time; equations treat x as a mystery number and undo one step at a time; and word problems take one calculation of the GSM8K solution at a time, with the sentence that explains it.

All answers are whole numbers except in the fractions and decimals topics. Word problems come from a bundled subset of 300 [GSM8K](https://github.com/openai/grade-school-math) training problems (MIT License; see `src/talk_with_reachy_math/math_data/GSM8K_LICENSE.txt`). The subset keeps problems of at most 35 words with a whole-number answer of at most 10,000 and drops topics that do not suit children, such as alcohol, gambling, weapons, and dieting. `deploy/make_word_problems.py` rebuilds it and turns each calculation of a GSM8K solution into a helper question.

Levels change by a fixed rule, separately for each topic and child:

- **Up one level** after three problems in a row answered right on the first try.
- **Down one level** after two problems in a row in which Reachy had to give away an answer, either to a helper question or to the problem.
- A problem solved with help, with every helper question answered right, changes nothing and starts both counts again.

Each child starts every topic at level 1. Their levels, counts, and current topic are saved in `people/<speaker ID>/math_progress.json` and uploaded with the rest of `people/`. Practice with a child whom voice ID cannot identify works the same way but is not saved.

### Logged events

| Event | Fields |
|---|---|
| `math_offer_prompted` | `speaker_id`: who was speaking when the offer note was sent. |
| `math_problem` | `problem_id` (`M001`, `M002`, … per app run), `asked_to`, `skill`, `level`, `standards`, `text` (what Reachy was given to read), `answer`, `source` (`generated`, or the GSM8K line such as `gsm8k-train-123`). |
| `math_answer` | `problem_id`, `answered_by` (speaker ID when the answer was checked; it can differ from `asked_to` when another child answers), `heard` (the words Reachy passed on), `parsed` (the number read from them, empty if none), `step` (empty for an answer to the problem itself; 1, 2, … for an answer to that helper question), `attempt` (1, 2, … counting each checked answer to this problem; empty when no number was heard and no help was asked for), `correct` (whether this answer was right for the problem or for the helper question), `close` (first answer only: within 10 percent of the right answer), `seconds_since_asked`, and on the last answer `outcome` (`first_try`, `with_help`, or `missed`, as defined in the level rule above). |
| `math_level_change` | `speaker_id`, `skill`, `old_level`, `new_level`. |
| `math_problem_skipped` | A new problem was asked, or practice stopped, before the open one was answered. |
| `math_practice_stopped` | `reason`, and `results`: problems and first-try answers per speaker ID in this practice session. |

Limits to keep in mind:

- `heard` is what the speech server transcribed, passed on by the model. A misheard number is checked as heard. The utterance records next to it hold the transcript and audio clip for checking by hand.
- `seconds_since_asked` runs from the moment Reachy received the problem, so it includes the time Reachy took to read it aloud.
- The model decides when to call the math tools. If it skips `check_math_answer` and answers by itself, no `math_answer` event appears for that problem.
- The model may reword a helper question when it asks it. The `step` field records which helper question the code checked each answer against; the utterance records hold what Reachy actually said.

Set `TALK_WITH_REACHY_MATH_PRACTICE=0` to turn math practice off. The tools are in the default profile only; other profiles do not offer math practice unless `math_practice` is added to their tools.

## Privacy notes for the IRB application

- **Voiceprints are biometric identifiers.** HIPAA lists voice prints among the 18 identifiers that make health information identifiable. The voice library, the audio clips, and the transcripts linked to them are identifiable data.
- **Everyone near the robot is recorded,** not only consented participants. With automatic voices, the app also stores a voiceprint for anyone who speaks for two seconds or more. If the IRB requires that only enrolled participants be fingerprinted, this behavior has to be changed before data collection; it is not a setting today.
- **Audio leaves the robot.** By default (`HF_REALTIME_CONNECTION_MODE=deployed`), microphone audio is sent to a speech service that Pollen Robotics hosts on Hugging Face; this happens in the upstream app too. Speaker names, IDs, and remembered facts are now sent to that service as well, inside the speaker notes. To keep audio on your own hardware, use `local` mode with your own [speech-to-speech](https://github.com/huggingface/speech-to-speech) server (see the upstream README).
- **Voice identification itself stays on the robot.** Voiceprints are computed locally; they are uploaded only to the Google Drive account that signed in.
- **The robot holds a Google sign-in.** It is limited to the `drive.file` scope, so it cannot see anything in that Drive except the files this app created. Those files are all the uploaded study data, though. If the robot is lost, remove the app's access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions) (sign in with the account that the robot used).
- **Math results are per child.** With voice ID on, each child's math levels and every answer they gave are stored under their speaker ID and uploaded with the other study data.
- **Video is not recorded.** The camera is used only when Reachy calls its camera tool, and no image is saved.

## Setup, in order

### 1. Update the robot

This app needs `reachy-mini` 1.10.0rc5 or newer. Update the robot from Reachy Mini Control first, on a network where the robot has internet access and your computer can reach the robot. An iPhone Personal Hotspot did not allow the second part in our tests.

### 2. Google sign-in for the app (one time)

This app uses the same Google OAuth client as Talk with Reachy (Google Cloud project `talk-with-reachy`), so nothing new needs to be created in Google Cloud. `CLIENT_ID` in `src/talk_with_reachy_math/google_drive_upload.py` is already that client's ID.

The client secret is kept out of the code, because the GitHub repository is public. Copy `deploy/google_client_secret.txt` from the Talk with Reachy folder into this folder's `deploy/` (the file holds the secret as its only line). Git ignores this file. `deploy/publish_space.py` (step 3) writes the secret into the copy it uploads to the private Space, which is where robots install the app from, and `deploy/google_dry_run.sh` reads it on the Mac.

The Google consent screen, its home page, and its privacy policy belong to that shared client; they are set up in Talk with Reachy (its `deploy/site/`). Before the Google app is published, the privacy policy should also mention the math answers this app records.

### 3. Publish as a private Hugging Face Space

The easy way is one command in Terminal on a Mac:

```bash
bash deploy/publish_to_hf.sh
```

It sets up the Hugging Face tools inside `deploy/.deploy-venv` (nothing is installed system-wide), opens your browser to sign in to Hugging Face if needed, creates the private Space `<your-account>/talk_with_reachy_math`, and uploads the app. It stops if a Space with that name already exists and is public. Run it again after any code change to update the Space.

To do it by hand instead, create a new Space with SDK **Static** and visibility **Private**, then push this repository to it:

```bash
git lfs install                      # the avatars and images are stored with Git LFS
git remote add space https://huggingface.co/spaces/<your-account>/talk_with_reachy_math
git push space talk-with-reachy-math:main
```

Keep the `reachy_mini_python_app` tag in the YAML header of `README.md`. The Control App finds apps by that tag.

The two GitHub workflows that sync to Hugging Face (`sync-hf-space.yml`, `pr-hf-space-preview.yml`) still point at Pollen's Spaces. Delete them, or change the repository IDs if you want GitHub to publish for you.

### 4. Install on the robot

In Reachy Mini Control, sign in to Hugging Face with an account that can see the private Space. Open the app store and search for *Talk with Reachy Math*. The app appears with a **Private** badge; the store also has a *Private* filter. Install it like any other app. After publishing a new version, update or reinstall it the same way.

### 5. Sign in to Google Drive (one time per device)

Each device that uploads signs in once. Both use the same "Talk with Reachy Math" folder in My Drive.

**a. On the Mac, no robot needed.** Run:

```bash
bash deploy/google_dry_run.sh
```

It shows a code. Open [google.com/device](https://www.google.com/device) on any phone or computer, enter the code, and sign in with the Google account whose Drive should receive the files. The script then writes `connection_check.txt` to **My Drive → Talk with Reachy Math**, logs a two-line test conversation with the app's own code, and uploads it. It ends with "Everything works" and the names of the test files. You can delete them afterwards.

This checks the whole Google side before a robot is involved. It also signs in the Mac, which is what the app uses when it runs in the Reachy Mini Control simulation. If Google says the sign-in is not allowed, the account's administrators do not allow this app; that cannot be fixed from the app.

**b. On the robot,** once Talk with Reachy Math is installed and the robot is on the same network as the Mac, run on the Mac:

```bash
bash deploy/google_login_on_robot.sh            # or: ... google_login_on_robot.sh <robot-ip>
```

SSH asks for the robot's password, and the robot shows a new code. Enter it at google.com/device the same way. The sign-in is saved in `/home/pollen/.config/talk_with_reachy_math/google_token.json`, readable only by the `pollen` user. A running app picks it up on its next upload pass; no restart is needed. After this, the robot uploads on its own wherever it has internet.

### 6. Enroll participants

Start the app, then enroll each consented participant as described in [Managing voices](#managing-voices). Enroll the researchers who will be in the room as well (for example `R01`), so that their speech is labeled and is never mistaken for a participant's.

### 7. Check that it works

Start the app, say a few sentences to Reachy, and wait up to five minutes. In Google Drive, under **My Drive → Talk with Reachy Math**, you should see `transcripts/` (a JSONL and a CSV file), `audio/` (one folder of clips per run), and `people/`. On the robot, `ls ~/talk_with_reachy_math_data/transcripts` shows the local copies.

## Behavior to know about

- **Upload timing.** Files upload every five minutes while the app runs, and once more when it stops. A file that is still growing is uploaded again; Google Drive updates the same file instead of adding a copy.
- **Data volume.** Audio clips are 16 kHz, 16-bit mono WAV: about 1.9 MB per minute of speech by people. Reachy's own speech is not saved as audio, because its text is logged and its voice is synthesized.
- **Nothing is lost offline.** If the robot has no internet, is signed out, or loses power, the files stay on the robot. They upload on the next successful pass, including after the next app start. Local files are never deleted by the app, except by the `delete` voice command (voiceprint and memories only).
- **Sign-in can end,** for example when the password changes, when access is removed in the Google account settings, after six months without use, or every 7 days if the Google app was left in *Testing* status. The app then logs `upload_signed_out` and keeps writing locally; run `deploy/google_login_on_robot.sh` again.
- **The robot needs internet, not a computer.** At a site whose Wi-Fi requires a sign-in page, or that blocks devices, the robot cannot upload; files then wait on the robot until it reaches a network that works.
- **Shutdown.** When the app is stopped, it first writes the remaining records, then waits up to 8 seconds for the final upload, because the daemon terminates apps that take longer than 20 seconds to stop. Anything not uploaded then goes up on the next start.

## Settings

All settings are optional environment variables. You can put them in the app's `.env` file.

| Variable | Default | Purpose |
|---|---|---|
| `TALK_WITH_REACHY_MATH_LOGGING` | `1` | Set to `0` to turn all study logging off (transcripts, audio, voice ID). |
| `TALK_WITH_REACHY_MATH_VOICE_ID` | `1` | Set to `0` to turn voice identification off. People are then logged as `unknown`, and Reachy goes back to the official app's shared memory. |
| `TALK_WITH_REACHY_MATH_VOICE_MATCH_THRESHOLD` | `0.45` | Score needed to accept a voice match. |
| `TALK_WITH_REACHY_MATH_SAVE_AUDIO` | `1` | Set to `0` to stop saving audio clips. Voice ID still works. |
| `TALK_WITH_REACHY_MATH_DATA_DIR` | `~/talk_with_reachy_math_data` | Where study files are written. |
| `TALK_WITH_REACHY_MATH_ROBOT_ID` | host name | First part of each file name; use it to tell robots apart. |
| `TALK_WITH_REACHY_MATH_GOOGLE_CLIENT_ID` | `CLIENT_ID` in `google_drive_upload.py` | Google OAuth client ID. Google Drive upload is off when neither is set. |
| `TALK_WITH_REACHY_MATH_GOOGLE_CLIENT_SECRET` | `CLIENT_SECRET` in `google_drive_upload.py` (empty in git; filled in the private Space from `deploy/google_client_secret.txt`) | Google OAuth client secret. |
| `TALK_WITH_REACHY_MATH_GOOGLE_FOLDER` | `Talk with Reachy Math` | Name of the folder in My Drive. |
| `TALK_WITH_REACHY_MATH_ONEDRIVE_CLIENT_ID` | empty | Turns on OneDrive upload instead, where an institution has approved the app registration. Google Drive takes precedence when both are set. |
| `TALK_WITH_REACHY_MATH_ONEDRIVE_TENANT` | `TENANT` in `onedrive_upload.py` | Microsoft tenant for OneDrive. |
| `TALK_WITH_REACHY_MATH_UPLOAD_INTERVAL_S` | `300` | Seconds between upload passes. |
| `TALK_WITH_REACHY_MATH_PRACTICE` | `1` | Set to `0` to turn math practice off. |
| `TALK_WITH_REACHY_MATH_OFFER_AFTER_S` | `180` | Seconds after the greeting, the previous invitation, or the end of practice before Reachy invites the child to a math game again. |

## Where the changes are

| File | Change |
|---|---|
| `src/talk_with_reachy_math/study_log.py` | New. Session files (JSONL and CSV), events, clock checks, and the single worker thread that does all study writing. |
| `src/talk_with_reachy_math/study_recorder.py` | New. Turns realtime events into timed utterance records, saves audio clips, and sends speaker notes. |
| `src/talk_with_reachy_math/audio_timeline.py` | New. Keeps the last two minutes of sent microphone audio, indexed the way the speech server indexes it. |
| `src/talk_with_reachy_math/voice_id.py` | New. Speaker model, voice library, enrollment, and voice commands. |
| `src/talk_with_reachy_math/voice_files.py`, `voices_cli.py`, `deploy/voices.sh` | New. The `talk-with-reachy-math-voices` command and its Mac wrapper. |
| `src/talk_with_reachy_math/cloud_upload.py` | New. The background uploader that mirrors the data folder, shared by both cloud targets. |
| `src/talk_with_reachy_math/google_drive_upload.py`, `deploy/google_dry_run.*`, `deploy/google_login_on_robot.sh` | New. Google sign-in (device code), Drive upload, the `talk-with-reachy-math-google-login` command, and their Mac helpers. |
| `src/talk_with_reachy_math/onedrive_upload.py`, `deploy/onedrive_dry_run.*`, `deploy/copy_login_to_robot.sh` | New, currently off. Microsoft sign-in and OneDrive upload. |
| `src/talk_with_reachy_math/huggingface_realtime.py` | Passes speech, transcript, audio, and response events to `study_recorder`, and can add a system note to the conversation. |
| `src/talk_with_reachy_math/tools/background_tool_manager.py` | Logs `tool_started` and `tool_finished`. |
| `src/talk_with_reachy_math/prompts.py`, `tools/remember.py`, `tools/forget.py` | Per-person memory when voice ID is on. |
| `src/talk_with_reachy_math/console.py` | Logs microphone mute changes. |
| `src/talk_with_reachy_math/math_practice.py`, `tools/math_practice.py`, `math_data/`, `deploy/make_word_problems.py` | New. Math problems, answer checking, levels, the three math tools, and the GSM8K subset. `prompts.py` explains them to the model. |
| `profiles/default/profile.md` | Rewritten for children aged 10 to 13: a friendly robot coach with short sentences and everyday words, the math tools, and a greeting that invites the child to a math game. |
| `src/talk_with_reachy_math/main.py` | Starts and stops study logging around the conversation. |
| `tests/test_study_*.py`, `tests/test_voice_id.py`, `tests/test_audio_timeline.py`, `tests/test_google_drive_upload.py`, `tests/test_onedrive_upload.py` | New tests. Google, Microsoft Graph, and the speaker model are replaced by fakes. |
| Everything else | Package rename only (`reachy_mini_conversation_app` → `talk_with_reachy_math`). |

In the upstream README, the command `reachy-mini-conversation-app` is `talk-with-reachy-math` in this fork.
