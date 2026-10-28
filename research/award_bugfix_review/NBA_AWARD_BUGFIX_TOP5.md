# NBA award bug-fix comparison

Opt-in only; not deployed. No rejected shrink layer. Frozen capture: 2026-10-28T09:09:37.231481+00:00.

The **before** column recomputes the current code on the same frozen inputs as **after**. The separately saved published reference may differ because its collection time differs.

| Award | Rank | Before | Chance | After | Chance |
|---|---:|---|---:|---|---:|
| MVP | 1 | Shai Gilgeous-Alexander | 40.7% | Luka Doncic | 35.9% |
| MVP | 2 | Nikola Jokic | 24.5% | Shai Gilgeous-Alexander | 23.7% |
| MVP | 3 | Victor Wembanyama | 12.0% | Nikola Jokic | 7.9% |
| MVP | 4 | Luka Doncic | 5.9% | Anthony Edwards | 4.8% |
| MVP | 5 | Cade Cunningham | 3.4% | Alperen Sengun | 4.5% |
| DPOY | 1 | Victor Wembanyama | 48.5% | Walker Kessler | 26.5% |
| DPOY | 2 | Chet Holmgren | 12.6% | Victor Wembanyama | 16.7% |
| DPOY | 3 | Nikola Jokic | 5.2% | Chet Holmgren | 8.0% |
| DPOY | 4 | Scottie Barnes | 4.9% | Alperen Sengun | 5.2% |
| DPOY | 5 | Ausar Thompson | 4.2% | Luka Doncic | 4.9% |
| ROY | 1 | Cameron Boozer | 56.5% | Cameron Boozer | 38.1% |
| ROY | 2 | Yaxel Lendeborg | 29.1% | Yaxel Lendeborg | 34.6% |
| ROY | 3 | Caleb Wilson | 10.6% | Caleb Wilson | 14.1% |
| ROY | 4 | Darius Acuff Jr. | 2.9% | Darius Acuff Jr. | 11.6% |
| ROY | 5 | Darryn Peterson | 0.5% | Darryn Peterson | 0.6% |
| 6MOY | 1 | Ajay Mitchell | 78.9% | Ajay Mitchell | 32.4% |
| 6MOY | 2 | Grayson Allen | 9.4% | Payton Pritchard | 21.9% |
| 6MOY | 3 | Payton Pritchard | 4.0% | Jerami Grant | 12.3% |
| 6MOY | 4 | Brook Lopez | 3.0% | Grayson Allen | 11.5% |
| 6MOY | 5 | Obi Toppin | 1.9% | Ayo Dosunmu | 5.2% |

Validation: all four published top-15 name orders match the before calculation; every probability agrees within the published four-decimal rounding tolerance. Largest absolute probability difference: 4.9849011522523634e-05.
