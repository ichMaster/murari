# LEDGER

## Гіпотези
- [H1][confirmed] перше твердження — джерело: https://example.com/a — випробувано: 2
- [H2][refuted] хибне твердження — джерело: https://example.com/b
- [H3][partial] частково вірне — джерело: https://example.com/c — примітка: залежить від умов
- [H4][open] ще некопана ідея
- [H7][open] інвертована версія H3 — parents: H3 — mutation: invert
- [H9][open] схрещення H3 і H5 — parents: H3+H5 — mutation: combine

## Прогони
- 1: generate(агент) → H1..H4
- 2: evaluate(агент) → H1 confirmed, H2 refuted
- 3: oppose(користувач) → H1 контраргумент
- 4: mutate(invert, H3, агент) → H7

## Сухі прогони поспіль: 0
