# THE presentation: timed talking points

Script for [`PRESENTATION_Experiment_Presentation.pptx`](PRESENTATION_Experiment_Presentation.pptx) / `.pdf`. The same text is in each slide's speaker notes. Times assume about 150 words per minute.
**Total: about 4 min 51 s.**


## Slide 1 (0:00–0:16, ~16 s): Stress-testing a UDP file-transfer service on AWS

*On screen:* title / summary

Hi, I'm Nikhil. I deployed the course's file-transfer service on AWS, instrumented it, and ran three experiments: loss versus file size, the retry budget, and autoscaling under load. Spoiler: the biggest problem wasn't a knob we were told to turn.

## Slide 2 (0:16–0:43, ~27 s): The service: HTTP in front, UDP behind

*On screen:* architecture.png

A client GETs a file from the ALB. A gateway task takes one of four in-flight slots and speaks a custom UDP protocol through an NLB. The backend fetches the file from S3 and blasts it as 64-byte datagrams, and the client asks for missing chunks with RETY. Two details matter. Every RETY re-downloads the whole file from S3, and every round ends with a 2-second quiet timeout.

## Slide 3 (0:43–1:17, ~34 s): Knobs, and the three experiments I picked

*On screen:* title / summary

I picked one experiment per layer: the network in E1, the client protocol in E2, and the cloud control plane in E3. To measure anything, I added per-request stats headers, CloudWatch counters for both tiers, and a per-request budget override. E1 and E2 cells are three 60-second trials each. The override was essential: it let me sweep nine budgets on the same tasks with no redeploys, so task placement isn't a confound. The whole study cost roughly a dollar or two of Learner Lab credit.

## Slide 4 (1:17–1:43, ~26 s): Surprise: 0% simulated loss ≠ 0% loss

*On screen:* E1_retry_work_vs_loss.png

First surprise: my smoke test at zero simulated loss failed for everything 64 KB and up. 35% of a 1 MB burst never arrived. A bigger gateway still lost, and bypassing the NLB still lost. The backend's sends all succeeded, so unpaced bursts overflow the receiver. 4 KB sits exactly on the simulated-loss line, and bigger files sit 10 to 35 points above it.

## Slide 5 (1:43–2:18, ~35 s): E1: file size amplifies loss

*On screen:* E1_success_rate_vs_loss.png

E1, about a thousand requests. 4 KB barely notices loss. 16 KB is perfect to 10%, then drops to 48% at 20%. 64 KB goes from 80% to zero, and 1 MB never succeeds. Latency comes in 2-second steps, one per round, and failures are the slowest requests of all. Look at 16 KB at 20%: mean retry rounds is 4.55 out of 5, so it's literally running out of budget. And 64 KB fails even before simulated loss, because of the burst loss from the last slide.

## Slide 6 (2:18–2:54, ~36 s): E1: why retries can't catch up

*On screen:* E1_full_window_emf_counters.png

Why don't retries fix it? The client fires thousands of RETYs at once. The backend has 8 workers and a 32-slot queue, and each RETY costs an S3 GET, 155 ms for 1 MB. So about 98% are dropped: those blue spikes. And the backend keeps serving stale RETYs after a client gives up. In the 1 MB cells the backend dropped about 411 thousand RETYs and served only 4.4 thousand. Each round can recover only around 40 chunks, so no reasonable round count catches up with thousands of missing chunks.

## Slide 7 (2:54–3:30, ~36 s): E2: rounds buy success, paid for in tail latency

*On screen:* E2_success_vs_tail_latency.png

E2 fixes loss at 5% and sweeps the budget. For 16 KB, three rounds already give 98%. For 64 KB, the default five rounds give 57%, and twenty give 100%, but at a p95 of 32 seconds. Open attempts barely matter. So the default suits small files, and raising it just trades fast failures for slow successes. Look at the curve on the right: every extra round adds about 2 seconds of tail, and above roughly 25 rounds the ALB's 60-second idle timeout would cut the request off anyway.

## Slide 8 (3:30–4:08, ~38 s): E3: the gateway scales on its own rejections

*On screen:* E3_timeline_configA.png

E3 steps users up every 3 minutes. Two gateway tasks cap at about 2.7 successes per second, and beyond that requests get 503s. Successful traffic alone never crossed the scaling target. The scaler fired only because 503s inflated the request count, about 5 minutes late, and 1,771 requests were rejected meanwhile. You can see it in the second panel: green, the successes, stays flat at 2.7 per second while orange, the 503s, climbs to 8 per second. Once four tasks were up, successes jumped to 4.7 per second, just as the load step ended.

## Slide 9 (4:08–4:33, ~25 s): E3: CPU scaling is blind here

*On screen:* E3_configA_ecs_cpu_memory.png

The backend never scaled. CPU stayed under 3% while 7 of 8 workers were busy. Both tiers wait on timeouts and S3 rather than compute, and the NLB offers no request metric. Scale-in also needs 15 quiet minutes, which a cooldown change can't shorten. My instrumentation counters, busy workers and overload drops, are exactly the custom metrics a scaling policy should track here.

## Slide 10 (4:33–4:51, ~18 s): Takeaways and recommendations

*On screen:* title / summary

Four recommendations. Pace the burst or use bigger chunks. Cache the file per transfer so a RETY is cheap. Make the retry budget size-aware. And scale each tier on what actually saturates, in-flight slots and busy workers, not 503-inflated request counts or idle CPU. Thanks!
