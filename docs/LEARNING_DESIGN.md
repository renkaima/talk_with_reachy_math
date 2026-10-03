# Learning design: why the math games work the way they do

Talk with Reachy Math plays spoken math games with children aged about 10 to 13 (US grades 5 to 7). This document explains each design choice in the games, names the learning theory behind it, and summarizes the studies that support it. It is written for researchers who plan a study with the app and for reviewers who want to know why the app does what it does.

The studies below motivated the design; none of them tested this app. Most tested other games, tutors, and robots, often on screens and with children of other ages. The last section lists these gaps, and the section before it lists what the app logs so that a study can check whether each choice works here.

## Overview

The design pursues three goals: the child wants to keep playing, the child practices the math that matters for their grade, and the child can follow everything by ear, because Reachy speaks and nothing is shown on a screen.

| Design choice | Goal | Theory | Main evidence | Where in the code |
|---|---|---|---|---|
| The child picks one of two games each round | keep playing | self-determination theory: autonomy | Patall et al. (2008); Cordova & Lepper (1996) | `MathCoach._next_offer`, `greeting_with_game_choice` |
| Story adventure: each problem moves the story on | keep playing, practice | intrinsic integration; contextualization | Habgood & Ainsworth (2011); Cordova & Lepper (1996) | `math_games._story` |
| Themes from what the child likes | keep playing | context personalization | Walkington (2013); Cordova & Lepper (1996) | `math_games.THEMES`, `Learner.theme` |
| Fix my mistakes, then "What did I do wrong?" | practice | learning from erroneous examples; learning by teaching; self-explanation | Adams et al. (2014); Chase et al. (2009); Tanaka & Matsuzoe (2012); Rittle-Johnson et al. (2017) | `math_games._fix_my_mistake` |
| Number riddles with clues | keep playing, practice | information-gap theory of curiosity | Loewenstein (1994) | `math_games._riddles` |
| Closest guess: estimate, then compare | practice | numerical estimation; competence | Siegler & Booth (2005); Ryan & Deci (2000) | `math_games._closest_guess` |
| Helper questions, one small step at a time | practice | scaffolding | Wood et al. (1976) | `Step`, `MathCoach.check_answer` |
| Different topics mixed within a story or mistake round | practice | interleaved practice | Rohrer et al. (2015) | `_STORY_PARTS`, `_MISTAKES` |
| Short sentences and familiar words | follow by ear | cognitive load theory; readability | Sweller (1988); Chall & Dale (1995) | `tests/test_kid_words.py` |
| Few, purposeful robot behaviors; prompts to explain | practice | social robots as tutors | Kennedy et al. (2015); Ramachandran et al. (2018); Belpaeme et al. (2018) | `prompts.MATH_GUIDANCE`, default profile |

## 1. The child picks the game

**What the app does.** At the start of a conversation and after every round of five problems, Reachy offers two of the five games, and the child picks one. The two games offered rotate, so every game comes up within three rounds.

**Why.** Self-determination theory holds that people are more intrinsically motivated when their need for autonomy is supported, together with their needs for competence and relatedness (Ryan & Deci, 2000). Offering choices is one way to support autonomy. A meta-analysis of 41 studies found that providing choice enhanced intrinsic motivation, effort, task performance, and perceived competence (Patall et al., 2008). The effect on intrinsic motivation was stronger for children than for adults and when two to four successive choices were given. In a study with elementary school children who practiced order-of-operations rules on a computer, offering choices about incidental parts of the learning context increased motivation, depth of engagement, and learning (Cordova & Lepper, 1996).

**How this shaped the design.** Reachy offers two games rather than all five, so that the choice stays quick when it is spoken. Patall et al. (2008) also found that choices between activities had a weaker effect than choices that were irrelevant to the instruction. The app therefore offers a second kind of choice that does not change the math: the theme of a story (section 3).

## 2. Story adventure: the math moves the story on

**What the app does.** A story round is a five-part adventure, such as a trip to the moon. Each part needs one problem solved to go on. For example, "Oh no, we are stuck! To get going, we need 3 fourths of our 24 moon rocks. How many moon rocks is that?" After the fifth part, Reachy reads the end of the story.

**Why.** Habgood and Ainsworth (2011) compared versions of a math game for children aged 7 to 11. In the intrinsic version, the math was part of the game's core mechanic; in the extrinsic version, the same math content was kept apart from it. Children learned more from the intrinsic version, and when they could choose freely, they played it about seven times longer. Cordova and Lepper (1996) found that presenting the same arithmetic in a meaningful and appealing context, rather than abstractly, increased motivation and learning.

**How this shaped the design.** In each part, the problem is the action that moves the story on (packing boxes, sharing with friends, fixing a problem, saving money at a shop, counting what we have). The problem is not a reward or a gate placed between story lines. The numbers stay small enough to work out in one's head while listening (section 8).

## 3. Themes from what the child likes

**What the app does.** Stories and the closest guess game use one of seven themes: space, dogs, soccer, dinosaurs, pizza, the ocean, or video games. When Reachy learns what a child likes, it passes the closest theme to the app, which saves it in the child's progress file and uses it in later rounds.

**Why.** Context personalization means placing problems in the context of a learner's out-of-school interests. Walkington (2013) randomly assigned 145 ninth-grade algebra students to normal or interest-personalized story problems in an intelligent tutoring system. Students who received personalized problems solved them faster and more accurately, the effect was largest for students who were struggling, and the benefit carried over to later, normal problems. Cordova and Lepper (1996) found that individually personalized versions of a learning context increased motivation and learning in elementary school children.

**How this shaped the design.** Walkington's study personalized problems to each student's reported interests. This app uses a fixed list of seven themes, which is a shallower form of personalization; section 10 discusses this limit.

## 4. Fix my mistakes

**What the app does.** Reachy shows its own work with one common mistake and asks the child for the real answer: "Can you check my work? I tried 1 half plus 1 third. I added the top numbers and the bottom numbers. I got 2 fifths. What is the real answer?" Each round shows five different mistakes, drawn from seven: adding the tops and the bottoms of two fractions, adding the digits after the decimal point as whole numbers, working left to right instead of times before plus, taking away a negative as if it were positive, forgetting the ones when multiplying, taking away a percent as if it were a plain number, and doing the opposite step in an equation. If the child repeats Reachy's wrong answer, Reachy says that it got that too, and they check it together with helper questions. When the child gets the real answer on the first try, Reachy asks, "What did I do wrong?"

**Why.** Three lines of research support this game.

- *Learning from erroneous examples.* Adams et al. (2014) had sixth and seventh graders learn decimals with a web-based tutor. One group corrected and explained erroneous worked examples, and the other solved problems. The two groups did equally well right after the lesson, but on a test one week later, the group that had worked with errors did better.
- *Learning by teaching.* Chase et al. (2009) found a "protégé effect": students made greater effort to learn for a computer agent they taught than for themselves. In their first study, eighth graders who believed they were teaching spent more time on learning activities and learned more, and lower-achieving students benefited most. Their second study, with fifth graders, suggested that a protégé lets students acknowledge errors while protecting their egos. Tanaka and Matsuzoe (2012) brought a robot that receives instruction from children into a classroom of 3- to 6-year-olds and found that it helped them learn English verbs.
- *Self-explanation.* A meta-analysis of prompted self-explanation in mathematics found small to moderate immediate improvements in procedural knowledge, conceptual knowledge, and procedural transfer (Rittle-Johnson et al., 2017). Its recommendations include prompting learners to explain why common misconceptions are incorrect, which is what "What did I do wrong?" asks.

**How this shaped the design.** The robot, not the child, makes the mistake. The child takes the teacher's role, and nobody has to admit their own error. Rittle-Johnson et al. (2017) also note that evidence for lasting effects of self-explanation, and for effects in classrooms, is limited, so the prompt is short and is asked once per problem.

## 5. Number riddles

**What the app does.** "I'm thinking of a number between 20 and 30. It is odd. It is in the 3 times table. What is my number?" The app chooses the clues so that exactly one number fits all of them. A wrong guess hears the first clue it does not fit ("24 does not fit this clue: it is odd."), and the helper questions add one more clue at a time.

**Why.** Loewenstein's (1994) information-gap theory explains curiosity as a response to a gap between what one knows and what one wants to know. A riddle opens such a gap, and each clue narrows it, which invites the child to reason about properties of numbers, such as even and odd, multiples, and digits (Common Core standard 4.OA.4, factors and multiples). Telling the child which clue their guess breaks turns a wrong guess into a reason to check that property again, instead of a plain "no".

## 6. Closest guess

**What the app does.** "6 boxes have 49 moon rocks in each. About how many moon rocks is that? Just guess, then I will guess too." Any number counts as a guess. Reachy then says its own guess, the real answer, and whose guess was closer, and it shares the rounding trick ("49 is close to 50. 50 times 6 is 300.").

**Why.** Estimation is part of numerical understanding; Siegler and Booth (2005) review how children's numerical estimation develops. The Common Core asks students to assess the reasonableness of answers with mental computation and estimation strategies, including rounding (standard 4.OA.3). The game also supports the need for competence in self-determination theory (Ryan & Deci, 2000). Reachy's guess is off by about 20 to 25 percent, so a child who rounds sensibly usually wins, and the trick that wins is said aloud right afterward.

## 7. Rounds, helper questions, and levels

**Helper questions (scaffolding).** When an answer is not right yet, Reachy does not give the answer or a long hint. It asks the problem's helper questions, one small step at a time ("Let's break 75 into 70 and 5. What is 70 times 9?"), and the app checks each answer. Wood, Bruner, and Ross (1976) described this kind of tutoring as scaffolding: the tutor takes over the parts of a task that the learner cannot yet manage and hands control back as the learner succeeds.

**Mixing topics (interleaving).** A story round and a "fix my mistakes" round each mix five different kinds of problems. Rohrer et al. (2015) gave 126 seventh graders the same practice problems over three months, arranged either in blocks of the same kind or interleaved. Interleaved practice led to higher scores on unannounced tests one day and 30 days later. Quick math keeps one topic for five problems, as before.

**Levels.** Each child has a level from 1 to 3 per topic and per game. Three right first answers in a row move the child up; two problems in a row in which Reachy had to give away an answer move the child down. This rule is a simple heuristic; it is not calibrated to a target success rate.

## 8. Words a child can follow by ear

**What the app does.** Every text that the app gives Reachy to read (problems, helper questions, explanations, story lines, and riddle clues) has sentences of at most 15 words. Every word is on the Dale-Chall list of about 3,000 words that fourth-grade American students could reliably understand (Chall & Dale, 1995), or is a math word taught in school (such as "fraction", "percent", or "parentheses"), or a theme word (such as "pizza"). `tests/test_kid_words.py` generates problems from every game, topic, level, and theme and checks them against these rules. Reachy is told to read these texts exactly as written, and to use short sentences and everyday words when it speaks in its own words.

**Why.** A child who only hears a problem cannot read it again; the whole problem has to be held in mind while working on it. Cognitive load theory holds that working memory is limited and that processing which uses up this capacity leaves less for learning (Sweller, 1988). Short sentences, familiar words, and one question at a time keep the load of listening low, so that more capacity is left for the math. The Dale-Chall list is based on fourth graders, a grade below the youngest children the app is for, which makes it a conservative standard.

**Limits of the check.** The test checks the texts the app writes. It does not check the words Reachy chooses itself, for example when it praises a child or chats.

## 9. How Reachy behaves as a tutor

Belpaeme et al. (2018) review how social robots have been used in education, the outcomes expected from them, and the technical challenges. Two findings from this research shaped this app.

- Kennedy, Baxter, and Belpaeme (2015) found that children learned about prime numbers from a robot that used a tutoring strategy, but did not learn a significant amount when the robot added more social and adaptive behavior. Reachy's prompt therefore keeps the math central: replies are short, movements such as a happy emotion accompany praise rather than replace it, and Reachy always says something after a math result.
- Ramachandran et al. (2018) found, with mostly sixth-grade students, that a robot tutor improved immediate learning gains and that prompting students to think aloud improved gains measured about a week later. "What did I do wrong?" and the helper questions ask children to put their thinking into words.

## 10. What the app logs to study these choices

| Question for a study | Logged data |
|---|---|
| Which games do children pick, and how long do they keep playing? | `math_problem.game`, `round`, `position`; `math_practice_stopped`; the utterance records |
| Does personalization change engagement? | `math_problem.theme`; the child's saved theme in `math_progress.json` |
| Do children accept or catch Reachy's mistakes? | `math_problem.reachy_answer` and the `math_answer` events that follow; the child's answer to "What did I do wrong?" is in the utterance records |
| How do children reason about riddle clues? | `math_answer.clue_missed`, `attempt`, `step` |
| How close are children's estimates? | `math_answer.parsed`, `reachy_guess`, `winner`, `close` |
| How much help do children need, per topic and game? | `math_answer.outcome` (`first_try`, `with_help`, `missed`); `math_level_change` |
| Do children drift off, and does Reachy bring them back? | `math_steer_prompted`, `math_offer_prompted` |

[STUDY_SETUP.md](../STUDY_SETUP.md#logged-events) describes every field.

## 11. Limits of this evidence

- **No study has tested this app.** The studies above tested other systems: computer games, intelligent tutors, teachable agents, and other robots. Whether these games help children learn or keep them engaged is an empirical question for a study with this app.
- **Different ages and settings.** Some findings come from younger children (Tanaka & Matsuzoe, 2012, ages 3 to 6) or older students (Walkington, 2013, ninth grade), and most from screen-based activities rather than spoken interaction with a robot.
- **Choice between activities.** The effect of choice on intrinsic motivation was weaker for choices between activities than for choices that did not affect the instruction (Patall et al., 2008).
- **Shallow personalization.** The seven themes are a fixed list. They personalize the setting of a problem, not its quantities or the child's own experiences, which is a weaker form of personalization than in Walkington (2013).
- **Short sessions.** The benefits of interleaving (Rohrer et al., 2015) and of erroneous examples (Adams et al., 2014) appeared on delayed tests after repeated practice. A single conversation with Reachy is much shorter.
- **The word list is from 1995 and in US English.** Some familiar words today, such as "pizza" and "soccer", had to be added by hand.

## References

Adams, D. M., McLaren, B. M., Durkin, K., Mayer, R. E., Rittle-Johnson, B., Isotani, S., & van Velsen, M. (2014). Using erroneous examples to improve mathematics learning with a web-based tutoring system. *Computers in Human Behavior, 36*, 401–411. https://doi.org/10.1016/j.chb.2014.03.053

Belpaeme, T., Kennedy, J., Ramachandran, A., Scassellati, B., & Tanaka, F. (2018). Social robots for education: A review. *Science Robotics, 3*(21), eaat5954. https://doi.org/10.1126/scirobotics.aat5954

Chall, J. S., & Dale, E. (1995). *Readability revisited: The new Dale-Chall readability formula*. Brookline Books.

Chase, C. C., Chin, D. B., Oppezzo, M. A., & Schwartz, D. L. (2009). Teachable agents and the protégé effect: Increasing the effort towards learning. *Journal of Science Education and Technology, 18*(4), 334–352. https://doi.org/10.1007/s10956-009-9180-4

Cordova, D. I., & Lepper, M. R. (1996). Intrinsic motivation and the process of learning: Beneficial effects of contextualization, personalization, and choice. *Journal of Educational Psychology, 88*(4), 715–730. https://doi.org/10.1037/0022-0663.88.4.715

Habgood, M. P. J., & Ainsworth, S. E. (2011). Motivating children to learn effectively: Exploring the value of intrinsic integration in educational games. *Journal of the Learning Sciences, 20*(2), 169–206. https://doi.org/10.1080/10508406.2010.508029

Kennedy, J., Baxter, P., & Belpaeme, T. (2015). The robot who tried too hard: Social behaviour of a robot tutor can negatively affect child learning. In *Proceedings of the Tenth Annual ACM/IEEE International Conference on Human-Robot Interaction* (pp. 67–74). ACM. https://doi.org/10.1145/2696454.2696457

Loewenstein, G. (1994). The psychology of curiosity: A review and reinterpretation. *Psychological Bulletin, 116*(1), 75–98. https://doi.org/10.1037/0033-2909.116.1.75

National Governors Association Center for Best Practices & Council of Chief State School Officers. (2010). *Common Core State Standards for Mathematics*. https://www.thecorestandards.org/Math/

Patall, E. A., Cooper, H., & Robinson, J. C. (2008). The effects of choice on intrinsic motivation and related outcomes: A meta-analysis of research findings. *Psychological Bulletin, 134*(2), 270–300. https://doi.org/10.1037/0033-2909.134.2.270

Ramachandran, A., Huang, C.-M., Gartland, E., & Scassellati, B. (2018). Thinking aloud with a tutoring robot to enhance learning. In *Proceedings of the 2018 ACM/IEEE International Conference on Human-Robot Interaction* (pp. 59–68). ACM. https://doi.org/10.1145/3171221.3171250

Rittle-Johnson, B., Loehr, A. M., & Durkin, K. (2017). Promoting self-explanation to improve mathematics learning: A meta-analysis and instructional design principles. *ZDM Mathematics Education, 49*(4), 599–611. https://doi.org/10.1007/s11858-017-0834-z

Rohrer, D., Dedrick, R. F., & Stershic, S. (2015). Interleaved practice improves mathematics learning. *Journal of Educational Psychology, 107*(3), 900–908. https://doi.org/10.1037/edu0000001

Ryan, R. M., & Deci, E. L. (2000). Self-determination theory and the facilitation of intrinsic motivation, social development, and well-being. *American Psychologist, 55*(1), 68–78. https://doi.org/10.1037/0003-066X.55.1.68

Siegler, R. S., & Booth, J. L. (2005). Development of numerical estimation: A review. In J. I. D. Campbell (Ed.), *The handbook of mathematical cognition*. Psychology Press. https://doi.org/10.4324/9780203998045-20

Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science, 12*(2), 257–285. https://doi.org/10.1207/s15516709cog1202_4

Tanaka, F., & Matsuzoe, S. (2012). Children teach a care-receiving robot to promote their learning: Field experiments in a classroom for vocabulary learning. *Journal of Human-Robot Interaction, 1*(1), 78–95. https://doi.org/10.5898/JHRI.1.1.Tanaka

Walkington, C. A. (2013). Using adaptive learning technologies to personalize instruction to student interests: The impact of relevant contexts on performance and learning outcomes. *Journal of Educational Psychology, 105*(4), 932–945. https://doi.org/10.1037/a0031882

Wood, D., Bruner, J. S., & Ross, G. (1976). The role of tutoring in problem solving. *Journal of Child Psychology and Psychiatry, 17*(2), 89–100. https://doi.org/10.1111/j.1469-7610.1976.tb00381.x
