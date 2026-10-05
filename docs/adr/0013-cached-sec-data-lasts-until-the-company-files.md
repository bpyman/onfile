# Cached SEC data lasts until the company files again

The live runtime caches each company's SEC data on disk: its company facts and its submissions list. A cached file has been trusted for one hour and then fetched again. Cold fetches are most of a live turn's time: a cold "top 10 banks by revenue" waits on 21 SEC requests, while the same turn on a warm cache takes about a second. The hour also bought little safety: a company's quarterly figures change only when it files a 10-Q, a 10-K or an amendment, a few times a year. A file fetched minutes before a filing was still trusted for most of an hour after it.

SEC publishes its latest filings as a feed (`browse-edgar?action=getcurrent`, Atom). Asked for `10-Q` it lists 10-Qs and 10-Q/As, and for `10-K` 10-Ks and 10-K/As, newest first, 100 to a page, each with the filer's CIK, the form, the accession number and the time SEC accepted it. When filings are quiet a page reaches back several days; in earnings season it may cover an hour or two.

## Decision

- **A filing watch reads the feed** every five minutes (`SEC_FILING_WATCH_SECONDS`, 300 by default; 0 turns it off). Each poll asks for 10-Qs and 10-Ks and pages back until it overlaps the previous poll. That is two requests every five minutes, through the same rate limiter as every other SEC request, and charged to no visitor's budget.
- **A company's cached files last until it files again.** The files are its company facts, its submissions list and its older submission pages. While the watch is healthy and has covered the time since a file was written, the file stays fresh for up to seven days, unless the company has filed a 10-Q, 10-K or amendment since.
- **After a filing, the company's files expire after 15 minutes, for a day.** SEC's structured data includes a filing some time after the filing itself appears, sometimes hours later. Until it does, the answer already says so ("SEC's structured data does not yet include this quarter's filing"), and a short expiry picks up the new quarter soon after it lands.
- **Whenever the watch cannot vouch for a file, the hour applies.** That covers a file written before the watch's coverage began (at startup, or after a poll found a gap it could not close by paging), a watch that has not polled successfully in three intervals, and a watch that is turned off. The ticker map and anything without a company keep the hour.
- **The parsed facts kept in memory follow the files.** Their key is the file's stamp, so a refetched file is parsed again.

## Consequences

- A cached company is answered without asking SEC for up to a week. A stale answer is possible only between a filing and the next poll (up to five minutes), and only for that company.
- The watch needs the process to stay up. On a plan that sleeps, a woken process starts with no coverage, so every file falls back to the hour until the watch has polled.
- Seven days bounds what the watch cannot see: SEC reprocessing a company's structured data without a new filing, or a filing type the watch does not read. Both are rare and neither is a 10-Q or 10-K.
- The recorded runtime has no cache and no watch, so tests and recorded answers do not change.

## Considered options

- **Keep the hour.** Simple, but every company is fetched again hourly whatever it filed, and a filing can still go unseen for up to an hour.
- **Stale-while-revalidate.** Serve the cached answer and fetch in the background, updating the answer if it changed. The window would have to change an answer the visitor is reading, and the stale case falls on filing day, when "the latest quarter" is most likely to be asked.
- **Predict filing dates from each company's history.** Filing deadlines and habits are regular, but amendments, early and late filers are not, and a prediction pays off only for per-company checks. One feed covers every company in two requests.
- **Ask SEC per company before each turn.** One small submissions request per company instead of the facts download, but still a request per company per turn, where the feed is two requests every five minutes for all of them.
