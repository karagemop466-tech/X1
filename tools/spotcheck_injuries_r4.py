#!/usr/bin/env python3
"""Round-4 spot check of the Week 10 injury table against the live nfl.com page (session arena-fb9e0427-x1).

The page values below were transcribed from fetch_page('https://www.nfl.com/injuries/') on 2026-11-15,
chunk 0 of 8, for the four clubs whose blocks are complete in that chunk: WAS, NYG, NE, DET.
Each is compared field by field against data/injuries/injuries_2026_week10.csv (snapshot 2026-11-14).
Writes data/audit/round4_spotcheck_injuries.csv. A spot check of 4 of 28 clubs is not a full re-verification.
Exit 1 if any field differs. Re-run: python3 tools/spotcheck_injuries_r4.py
"""
import csv, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = "https://www.nfl.com/injuries/"
FETCHED = "2026-11-15"
# Transcribed from fetch_page https://www.nfl.com/injuries/ (chunk 0 of 8, read 2026-11-15).
# Fields: team, player, position, injuries, practice, game status (blank = printed blank).
F = {
 "WAS": [
  ("John Bates","TE","","Full Participation in Practice",""),
  ("Treylon Burks","WR","","Did Not Participate In Practice",""),
  ("Jayden Daniels","QB","","Full Participation in Practice",""),
  ("Matt Gulbin","C","","Full Participation in Practice",""),
  ("Chig Okonkwo","TE","","Full Participation in Practice",""),
  ("Lucas Patrick","C","Concussion","Did Not Participate In Practice","Out"),
  ("Amik Robertson","CB","","Limited Participation in Practice",""),
  ("Shy Tuttle","DT","","Full Participation in Practice",""),
  ("Colson Yankoff","TE","Knee","Did Not Participate In Practice","Out"),
 ],
 "NYG": [
  ("Abdul Carter","LB","","Full Participation in Practice",""),
  ("Jermaine Eluemunor","T","","Full Participation in Practice",""),
  ("Malik Harrison","LB","Groin","Limited Participation in Practice","Questionable"),
  ("Colton Hood","CB","","Full Participation in Practice",""),
  ("Theo Johnson","TE","","Full Participation in Practice",""),
  ("Charlie Jones","WR","","Full Participation in Practice",""),
  ("J.J. McCarthy","QB","","Full Participation in Practice",""),
  ("Darnell Mooney","WR","","Full Participation in Practice",""),
  ("Malik Nabers","WR","","Full Participation in Practice",""),
  ("Cam Skattebo","RB","","Full Participation in Practice",""),
  ("Andrew Thomas","T","","Full Participation in Practice",""),
 ],
 "NE": [
  ("Ben Brown","C","Knee","Did Not Participate In Practice","Out"),
  ("A.J. Brown","WR","Ankle, Knee","Limited Participation in Practice","Questionable"),
  ("Kevin Byard","S","Chest","Full Participation in Practice","Questionable"),
  ("Carlton Davis III","CB","Knee","Did Not Participate In Practice","Out"),
  ("Reggie Gilliam","FB","Knee","Limited Participation in Practice","Questionable"),
  ("TreVeyon Henderson","RB","Illness","Did Not Participate In Practice","Out"),
  ("Hunter Henry","TE","","Limited Participation in Practice",""),
  ("Cameron Latu","TE","Back","Limited Participation in Practice","Questionable"),
  ("Drake Maye","QB","","Full Participation in Practice",""),
  ("Morgan Moses","T","","Full Participation in Practice",""),
  ("Walter Rouse","T","Concussion","Limited Participation in Practice","Questionable"),
  ("Brenden Schooler","S","Hamstring","Limited Participation in Practice","Questionable"),
  ("Rhamondre Stevenson","RB","Knee","Limited Participation in Practice","Questionable"),
  ("Greg Van Roten","G","Hamstring","Full Participation in Practice","Questionable"),
  ("Charles Woods","CB","Hamstring","Full Participation in Practice","Questionable"),
 ],
 "DET": [
  ("Brian Branch","S","","Full Participation in Practice",""),
  ("Jared Goff","QB","","Full Participation in Practice",""),
  ("Kerby Joseph","S","Knee","Did Not Participate In Practice","Out"),
  ("Cade Mays","C","Ankle","Did Not Participate In Practice","Out"),
  ("D.J. Reed","CB","Hip","Did Not Participate In Practice","Out"),
  ("Jacob Saylors","RB","","Full Participation in Practice",""),
  ("Amon-Ra St. Brown","WR","Rib","Limited Participation in Practice","Questionable"),
  ("Sione Vaki","RB","Ankle","Limited Participation in Practice","Questionable"),
  ("DJ Wonnum","DE","","Full Participation in Practice",""),
 ],
}
repo = list(csv.DictReader(open(os.path.join(ROOT, "data/injuries/injuries_2026_week10.csv"), encoding="utf-8-sig")))
out = []
for team, rows in F.items():
    rr = [r for r in repo if r["team"] == team]
    names = {r["player"]: r for r in rr}
    for (pl, pos, inj, prac, gm) in rows:
        r = names.get(pl)
        if r is None:
            out.append([team, pl, pos, inj, prac, gm, "", "", "", "", "no", SOURCE, FETCHED]); continue
        same = all((r[k] or "") == pv for k, pv in (("position", pos), ("injuries", inj),
                                                  ("practice_status", prac), ("game_status", gm)))
        out.append([team, pl, pos, inj, prac, gm, r["position"], r["injuries"], r["practice_status"],
                    r["game_status"], "yes" if same else "no", SOURCE, FETCHED])
    for pl in names:
        if pl not in {x[0] for x in rows}:
            out.append([team, pl, "", "", "", "", names[pl]["position"], names[pl]["injuries"],
                        names[pl]["practice_status"], names[pl]["game_status"], "no", SOURCE, FETCHED])
hdr = ["team", "player", "page_position", "page_injuries", "page_practice", "page_game_status",
       "repo_position", "repo_injuries", "repo_practice", "repo_game_status", "match", "source_url", "fetched"]
with open(os.path.join(ROOT, "data/audit/round4_spotcheck_injuries.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh); w.writerow(hdr); w.writerows(out)
bad = [r for r in out if r[10] != "yes"]
print(f"players compared: {len(out)}; clubs: {len(F)}; mismatches: {len(bad)}")
for r in bad: print("  MISMATCH", r[:2], r[6:10])
sys.exit(1 if bad else 0)
