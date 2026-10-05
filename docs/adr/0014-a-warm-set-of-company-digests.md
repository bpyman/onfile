# A warm set of company digests, fetched in the background

> **Builds on [ADR 0013](0013-cached-sec-data-lasts-until-the-company-files.md).**

With cached data lasting until a company files again, a company's first question is the only one that waits on SEC. That first question is still slow: a large company's facts file is 6 to 9 MB, and a cold ten-bank ranking waits on 21 requests at the shared rate. Most questions are about large companies, so their data can be fetched before anyone asks.

What a lookup keeps of a facts file is small. The catalog's concepts, with the two summaries a lookup builds from the whole file (each filing's fiscal labels, and the periodic reports the file names), come to about 0.6 to 0.9 MB of JSON for a large company, about 50 KB gzipped, against 6 to 9 MB raw, and decode in 3 to 5 ms against 60 to 90 ms.

## Decision

- **A lookup keeps a company's digest on disk in place of its facts file.** The first parse of a facts file writes `digest-{cik}.json.gz` and deletes the raw file. The digest is dated when the facts file was fetched, so a filing in between still dates it, and it is as fresh as the facts file was, by ADR 0013's rule. A digest carries a tag made from its layout and the concepts a lookup reads, so one made by other code is fetched again rather than read.
- **A warm-up fetches the largest companies before anyone asks.** It is a background thread that starts with the filing watch, and only while the watch is on. It walks the largest snapshot members that file 10-Qs, largest first (`SEC_WARM_COMPANIES`, 250 by default; 0 turns it off), fetching each one's first submissions page and facts digest when the watch says it should:
  - when the company is not cached;
  - when it has filed since its files were written;
  - when its week is up.

  A company that filed within a day is left to its visitors, whose questions refresh it every 15 minutes while SEC's structured data catches up. Otherwise the warm-up would fetch it 96 times a day.
- **The warm-up never goes ahead of a visitor.** It keeps to its own share of the request rate (`SEC_WARM_REQUESTS_PER_SECOND`, 2 by default), within the shared limiter. It waits whenever a request is queued for a slot or SEC has asked for a pause. A company it cannot fetch is logged and left to the first turn that asks.

## Consequences

- After a deploy the app answers at once; the warm set fills behind it in about four minutes (250 companies, two requests each, at two a second). Until then, a cold company is fetched when asked, as before.
- The warm set takes about 15 MB of disk, gzipped. Its downloads are compressed on the wire, roughly 1 MB a company, so about 250 MB a deploy. A persistent disk would keep the set across deploys; nothing requires one.
- Within a day of filing, a warm company's next question may wait on SEC again, which is when its new quarter appears.

## Considered options

- **Keep raw facts files and warm fewer companies.** About 150 fit the disk cache's default cap at 6 to 9 MB each, and each still costs a 60 to 90 ms parse on its first question.
- **Hold the warm set in memory.** At 2.5 to 4 MB parsed a company, 250 would take most of a 512 MB instance; the memory layer stays at 32 companies.
- **Warm the whole snapshot.** About 5,200 companies: roughly 0.3 GB of digests on disk, but 10,000 requests and hours of background fetching after every deploy, for companies rarely asked about.
