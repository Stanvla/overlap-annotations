# Pravidla anotace překryvné řeči

Děkujeme za pomoc s anotací překryvné řeči. Cílem je označit úseky, ve kterých je kromě hlavního mluvčího slyšet také další mluvčí, a odlišit užitečné případy od šumu nebo běžného pozadí.

Tento dokument se zobrazí při prvním spuštění. Později ho můžete kdykoli znovu otevřít přes tlačítko **Info**.

## Co je cílem

Hledáme případy, kdy je v nahrávce slyšet **další lidská řeč překrývající se s hlavním mluvčím**. Ne každé pozadí je ale pro nás užitečné. Důležité je rozlišit, jestli jde o skutečný overlap, a pokud ano, jestli ho lze alespoň přibližně lokalizovat a přepsat.

### Jak chápat hlavního mluvčího

Hlavního mluvčího neurčujeme podle přepisu, ale podle audia. Za hlavního mluvčího považujeme toho, kdo je blíže mikrofonu, je hlasitější, srozumitelnější a tvoří hlavní foreground nahrávky.

Za overlap považujeme další lidskou řeč, která je slyšet přes tuto hlavní řeč nebo současně s ní.

Pokud je v rozhraní zobrazen přepis, berte ho jen jako pomocnou informaci. Přepis nemusí vždy odpovídat pouze hlavnímu mluvčímu a může obsahovat i řeč dalších mluvčích. Při rozhodování se proto vždy řiďte především tím, co skutečně slyšíte v audiu.

## Možnosti anotace

Při každém příkladu vyberte jednu z těchto možností:

### 1. Není užitečný overlap

Vyberte tuto možnost, pokud:
- je slyšet jen jeden mluvčí,
- není zřejmý žádný hlavní mluvčí, jen jen hluk, šum, hudba nebo dav na pozadí,
- jsou slyšet různé hlasy, ale jsou očividně daleko od mikrofonu; je možné, že jsou slyšet jednotlivá slova, ale souvislá řeč není rozpoznatelná, nejde o projev s překryvem.

V tomto případě se nic dalšího neoznačuje.

### 2. Overlap existuje, ale nelze ho spolehlivě lokalizovat

Vyberte tuto možnost, pokud je zřejmé, že je v nahrávce hlavní řečník a další překrývající se řeč, která není jen pozadí, ale nejste schopni rozumně určit, kde přesně začíná a končí.

V tomto případě se ukládá jen informace, že v nahrávce je překryv bez spanů (vyznačených úseků).

### 3. Overlap existuje a lze ho lokalizovat

Vyberte tuto možnost, pokud můžete označit konkrétní úsek nebo úseky, kde je slyšet další mluvčí.

V tomto případě přidejte jeden nebo více **spanů** tak, že je označíte myší. U každého spanu zvolte úroveň srozumitelnosti:
- **řeč je nesrozumitelná**,
- **řeč je částečně srozumitelná**,
- **řeč je dobře srozumitelná**.

U každého spanu můžete také vyplnit text, který říkal ten druhý řečník, pokud jste rozuměli. Rozhraní umožňuje označit span, opakovaně (i dokolečka) si jej poslouchat a průběžně ho upravovat tak, abyste pokryli celý úsek.

Pro lepší srozumitelnost rozhraní také umožňuje přehrávání zpomalit.

## Jak psát text

Text pište jen tehdy, když si jste tím, co slyšíte, alespoň částečně jistí. Není nutné doplňovat celou větu za každou cenu. Pokud rozumíte jen části, zapište jen tu část.


Pokud řeči nerozumíte, jen vyznačte úsek a text nechte prázdný. Pokud slyšíte jen část slova, není potřeba domýšlet celé slovo. V takovém případě napište například tři tečky, že se řeč usekla.

## Co se považuje za pozitivní případ

Pro tuto úlohu jsou **pozitivní** tyto dva případy:
- overlap existuje, ale nelze ho spolehlivě lokalizovat,
- overlap existuje a lze ho lokalizovat.

**Negativní** je pouze případ, kdy není užitečný overlap.

## Důležité zásady

- Neoznačujte jako overlap běžný hluk na pozadí.
- Neoznačujte jako overlap každou vzdálenou nebo neurčitou řeč v davu, jde nám o překryv řečníků, který “stojí za rozplétání”.
- Pokud si nejste jistí přesnými hranicemi, označte span přibližně, ale jen tehdy, když opravdu slyšíte dalšího mluvčího.

## Přerušení práce

- práci můžete přerušit kdykoli po uložení nějakého úseku (tj. po stisku tlačítka Submit)
- okno prohlížeče je při delším přerušení lepší zavřít a později otevřít nové
- zapomenete-li starší okno otevřené, neanotujte v něm dále, ale zavřete jej (a otevřte si nové)

## Praktické doporučení

- Klidně si příklad pusťte vícekrát.
- Nejprve se rozhodněte, jestli jde o negativní, nebo pozitivní případ.
- Teprve potom řešte přesnější lokaci a případný text.

Děkujeme. Vaše anotace pomohou vytvořit kvalitnější data pro rozpoznávání překryvné řeči.