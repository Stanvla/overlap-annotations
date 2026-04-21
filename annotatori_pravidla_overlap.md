# Pravidla anotace překryvné řeči

Děkujeme za pomoc s anotací překryvné řeči. Cílem je označit úseky, ve kterých je kromě hlavního mluvčího slyšet také další mluvčí, a odlišit užitečné případy od šumu nebo běžného pozadí.

Tento dokument se zobrazí při prvním spuštění. Později ho můžete kdykoli znovu otevřít přes tlačítko **Info**.

Anotace se ukládají po stisku tlačítka **Submit**, takže není potřeba nic ukládat zvlášť.

## Co je cílem

Hledáme případy, kdy je v nahrávce slyšet **další lidská řeč překrývající se s hlavním mluvčím**. Ne každé pozadí je ale pro nás užitečné. Důležité je rozlišit, jestli jde o skutečný overlap, a pokud ano, jestli ho lze alespoň přibližně lokalizovat a případně částečně přepsat.

### Jak chápat hlavního mluvčího

Hlavního mluvčího neurčujeme podle přepisu, ale podle audia. Za hlavního mluvčího považujeme toho, kdo je blíže mikrofonu, je hlasitější, srozumitelnější a tvoří hlavní foreground nahrávky.

Za overlap považujeme další lidskou řeč, která je slyšet přes tuto hlavní řeč nebo současně s ní.

Pokud je v rozhraní zobrazen přepis, berte ho jen jako pomocnou informaci. Přepis nemusí vždy odpovídat pouze hlavnímu mluvčímu a může obsahovat i řeč dalších mluvčích. Při rozhodování se proto vždy řiďte především tím, co skutečně slyšíte v audiu.

## Možnosti anotace

Při každém příkladu vyberte jednu z těchto možností.

### 1. Není užitečný overlap

Vyberte tuto možnost, pokud:
- je slyšet jen jeden mluvčí,
- není zřejmý žádný hlavní mluvčí a je slyšet jen hluk, šum, hudba nebo dav na pozadí,
- jsou slyšet různé hlasy, ale jsou očividně daleko od mikrofonu a nejde o překryv, který by stálo za to rozplétat,
- je slyšet jen velmi krátká nebo nevýznamná vložka druhého hlasu, například samotné „ehm“, „hm“, „uh“, krátké povzdechnutí, odkašlání nebo jiný podobný výplňový zvuk, který sám o sobě nepředstavuje užitečný překryv.

V tomto případě se nic dalšího neoznačuje.

### 2. Overlap existuje, ale nelze ho spolehlivě lokalizovat

Vyberte tuto možnost, pokud je zřejmé, že v nahrávce kromě hlavního mluvčího skutečně zaznívá další lidská řeč, ale nejste schopni ani přibližně určit, kde rozumně začíná a končí.

Tuto možnost použijte tehdy, když overlap slyšíte jako fakt, ale nedokážete vyznačit žádný smysluplný úsek. Nestačí tedy jen to, že si nejste jistí úplně přesnou hranicí. Pokud umíte overlap označit alespoň přibližně, patří do třetí kategorie.

V tomto případě se ukládá jen informace, že v nahrávce je překryv, bez spanů.

### 3. Overlap existuje a lze ho lokalizovat

Vyberte tuto možnost, pokud můžete označit konkrétní úsek nebo úseky, kde je slyšet další mluvčí, alespoň přibližně.

V tomto případě přidejte jeden nebo více **spanů** tak, že je označíte myší. U každého spanu zvolte úroveň srozumitelnosti:
- **řeč je nesrozumitelná** – nelze rozpoznat žádný smysluplný text,
- **řeč je částečně srozumitelná** – rozumíte jen části toho, co druhý mluvčí říká,
- **řeč je dobře srozumitelná** – lze rozumět většině nebo celému překryvu.

U každého spanu můžete také vyplnit text, který říkal druhý řečník, pokud jste mu rozuměli. Rozhraní umožňuje označený span opakovaně přehrávat a průběžně upravovat, aby co nejlépe pokrýval celý úsek.

Pro lepší srozumitelnost lze přehrávání také zpomalit.

## Doporučený postup v rozhraní

Nejprve vždy vyberte kategorii příkladu. Teprve pokud zvolíte možnost, že overlap lze lokalizovat, začněte označovat spany.

Postup je tedy tento:
1. nejprve se rozhodněte, zda jde o negativní případ, overlap bez spanu, nebo overlap se spanem,
2. pokud jde o lokalizovatelný overlap, označte příslušný span nebo spany,
3. nakonec případně doplňte srozumitelnost a text.

Rozhraní umožňuje span průběžně upravovat, takže není nutné trefit jeho hranice přesně napoprvé.

## Jak rozhodovat v hraničních případech

Pokud si nejste jistí úplně přesnými hranicemi, ale dokážete overlap přibližně umístit do konkrétní části nahrávky, zvolte **Overlap existuje a lze ho lokalizovat** a span vyznačte přibližně.

Pokud však overlap slyšíte jen obecně, ale nedokážete ani přibližně určit žádný rozumný úsek, zvolte **Overlap existuje, ale nelze ho spolehlivě lokalizovat**.

Krátké výplňové zvuky druhého mluvčího, například samotné „ehm“, „hm“, „uh“ a podobné nevýznamné vložky, obvykle **nepovažujte za užitečný overlap**.

## Jak psát text

Text pište jen tehdy, když si jste tím, co slyšíte, alespoň částečně jistí. Není nutné doplňovat celou větu za každou cenu. Pokud rozumíte jen části, zapište jen tu část.

Pokud řeči nerozumíte, jen vyznačte úsek a text nechte prázdný. Pokud slyšíte jen část slova, není potřeba domýšlet celé slovo. V takovém případě můžete ponechat text prázdný nebo naznačit neúplnost, pokud to považujete za užitečné.

## Co se považuje za pozitivní případ

Pro tuto úlohu jsou **pozitivní** tyto dva případy:
- overlap existuje, ale nelze ho spolehlivě lokalizovat,
- overlap existuje a lze ho lokalizovat.

**Negativní** je pouze případ, kdy není užitečný overlap.

## Přerušení práce

- Práci můžete přerušit kdykoli po odeslání příkladu, tedy po stisku tlačítka **Submit**.
- Okno prohlížeče je při delším přerušení lepší zavřít a později otevřít nové.
- Zapomenete-li starší okno otevřené, dále v něm neanotujte, ale zavřete jej a otevřete si nové.

## Návrat k předchozím příkladům

V průběhu školení ani během běžné anotace se nelze vracet k předchozím příkladům. Není ale potřeba se toho obávat.

Ve školení je to tak záměrně, protože příkladů je více a předpokládá se, že si pravidla postupně osvojíte.

V běžné anotaci se navíc řada příkladů záměrně ukazuje více anotátorům, takže jednotlivé případy bývají ověřeny opakovaně.

## Počítadlo postupu

Protože se příklady vybírají z dynamické fronty a některé mohou být průběžně posílány na kontrolu nebo opakovanou anotaci, rozhraní zobrazuje pouze počet již dokončených příkladů.

Počet zbývajících příkladů se proto nezobrazuje.

## Praktické doporučení

- Klidně si příklad pusťte vícekrát.
- Nejprve se rozhodněte, jestli jde o negativní, nebo pozitivní případ.
- Teprve potom řešte přesnější lokaci a případný text.
- Pokud si nejste jistí, řiďte se především tím, co skutečně slyšíte v audiu, ne tím, co byste očekávali z přepisu.

Děkujeme. Vaše anotace pomohou vytvořit kvalitnější data pro rozpoznávání překryvné řeči.