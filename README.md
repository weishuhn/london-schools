# London Secondary Schools

This is a list of London secondary schools ranked by their performance in the 2025 GCSE exams.  ./top-100-schools.txt is the source data.

The data was fetched from: 

curl 'https://dlv.tnl-parent-power.gcpp.io/2025?filterId=the-top-state-secondary-comprehensive-schools' \
  -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) Gecko/20100101 Firefox/148.0' \
  -H 'Accept: */*' \
  -H 'Accept-Language: en-US,en;q=0.9' \
  -H 'Accept-Encoding: gzip, deflate, br, zstd' \
  -H 'DNT: 1' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Connection: keep-alive' \
  -H 'Sec-GPC: 1' \
  -H 'If-None-Match: W/"9ddaf-RSLrZ6h8HPwSYMBvGnEjHhZ+BYc"' \
  -H 'Priority: u=0' \
  -H 'TE: trailers'

I would like to mash up the data with research on the top family neighbourhoods in London. 

As well as what properties are available near those schools:  https://github.com/scrapfly/scrapfly-scrapers/tree/main/rightmove-scraper