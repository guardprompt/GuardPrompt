> 🌐 **Kalba / Language:** **Lietuvių** · [English](LICENSING_INFO.md)

# GuardPrompt licencijavimo modelis

GuardPrompt licencijuojamas kaip **metinė on-premise prenumerata**, pagal organizacijos dydį.  
Klientas pats valdo, kiek vidinių vartotojų naudojasi sistema.

GuardPrompt **neskaičiuoja** ir nesekas aktyvių vartotojų.

---

## Organizacijos dydžio pakopos

Organizacijos pasirenka prenumeratos pakopą pagal apytikslį dydį:

- **Maža (S):** iki 50 darbuotojų  
- **Vidutinė (M):** 51–250 darbuotojų  
- **Didelė (L):** 251–1000 darbuotojų  
- **Įmonių (XL):** 1001–5000+ darbuotojų  

Šios pakopos naudojamos tik kainodarai — organizacija pati reguliuoja savo vartotojų skaičių.

---

## Kas įskaičiuota į metinę licenciją

- Neriboti dokumentai  
- Neribotas anonimizavimas ir ingestija  
- Neribotos RAG / DI užklausos  
- Pilna prieiga prie OpenWebUI integracijų  
- GuardPrompt Claude proxy (programuotojų įrankiai) ir Zabbix stebėsenos stekas  
- GPU pagreitinimo palaikymas  
- Visi atnaujinimai ir saugumo pataisos  
- On-premise diegimo teisės  

---

## Kas neįskaičiuota

Išorinių DI paslaugų mokesčiai (jei naudojami) **neįtraukti** į GuardPrompt licenciją.  
Tai apima:

- OpenRouter.ai  
- OpenAI API  
- Anthropic Claude  
- Gemini  
- Mistral  
- Bet kurį kitą trečiosios šalies LLM tiekėją  

Šias paslaugas atskirai apmokestina jų tiekėjai. Claude proxy pristatomas su
GuardPrompt, bet **jo relay'inama Anthropic prenumerata (Pro/Team) ar API raktas
yra kliento sąnaudos** — GuardPrompt jų nei teikia, nei apmokestina.

---

## Bandomoji licencija (30 dienų)

- Galioja 30 dienų  
- Iki 3 vartotojų  
- Neriboti dokumentai  
- Pilnas funkcionalumas  
- Pasibaigus, sistema pereina į **Ribotą režimą**, kol pritaikoma komercinė licencija  

## Bandomosios licencijos aktyvavimas

Norint aktyvuoti 30 dienų bandomąją licenciją, klientas turi pateikti konkrečią registracijos informaciją GuardPrompt tiekėjui.

### Reikalinga registracijos informacija

Anonimizatoriaus registracijos info:
- Host ID: pateikiama automatiškai
- Host IP: pateikiama automatiškai
- Data Till: nustatoma automatiškai
- Admin Email: (įveda vartotojas)
- Admin Pass: (įveda vartotojas)
- Users Count: 3

### Host ID ir Host IP gavimas

GuardPrompt turi lokalų endpoint'ą, kuris automatiškai pateikia reikiamus mašinos identifikatorius:

http://localhost:8005/api/reginfo

Šis endpoint'as grąžina arba reikalauja šių laukų:

- **Host ID** – unikalus aparatūrą atitinkantis anonimizatoriaus instancijos identifikatorius. Naudojamas licencijai, kriptografiškai susietai su šiuo diegimu, sugeneruoti (apsauga nuo neteisėto pakartotinio naudojimo).
- **Host IP** – serverio išorinis IP adresas, aptiktas registracijos metu. Naudojamas licencijos validavimui ir saugumo auditui.
- **Data Till** – bandomosios licencijos galiojimo pabaigos data. Šį lauką automatiškai nustato tiekėjas generuodamas bandomąją licenciją (30 dienų nuo aktyvavimo). Vartotojai jo nekeičia.
- **Admin Email** – įveda klientas. Tampa pagrindine administratoriaus paskyra, naudojama GuardPrompt vartotojams ir nustatymams.
- **Admin Pass** – įveda klientas. Saugus administratoriaus paskyros slaptažodis. Tiekėjas jo nenustato ir nežino.
- **Users Count: 3** – fiksuota bandomosios licencijos riba. Bandomoji versija palaiko iki trijų vidinių vartotojų. Padidinimas reikalauja komercinės licencijos.

### Administratoriaus kredencialai

Registracijos metu klientas turi pateikti:

- **Admin Email** – pagrindinė administratoriaus paskyra  
- **Admin Password** – pasirinktas pradinės sąrankos metu  
- **Users Count** – fiksuotas **3** bandomajai licencijai  

Jokios papildomos konfigūracijos nereikia.

### Licencijos pristatymas

Kai tiekėjas gauna registracijos informaciją, sugeneruojamas ir pateikiamas bandomasis licencijos raktas.  
Pritaikius raktą, aktyvuojamas pilnas **30 dienų bandomasis laikotarpis** su visomis platformos funkcijomis.

Pasibaigus bandomajam laikotarpiui, GuardPrompt automatiškai pereina į **Ribotą režimą**, kol pritaikoma komercinė licencija.

Dėl licencijos pristatymo ir pagalbos kreipkitės:

- **Telegram:** [@GuardPrompt](https://t.me/GuardPrompt)  
- **El. paštas:** [info@guardprompt.lt](mailto:info@guardprompt.lt)

---

## Atnaujinimas

Licencijos paprastai atnaujinamos **kasmet (min. 12 mėn.)**.  
Tačiau prenumeratos laikotarpis gali būti pritaikytas — tiekėjas ir klientas gali susitarti dėl **bet kokios licencijos trukmės**:

- 12 mėn. (standartas)
- 18 mėn.
- 24 mėn.
- 36 mėn.
- Individualus įmonės terminas

Jei licencija baigiasi, GuardPrompt lieka įdiegtas, bet pereina į **Ribotą režimą**, kol aktyvuojama nauja licencija.

---

## Licencijos atsakomybė

Klientas atsako už:

- vidinės prieigos valdymą  
- vartotojų skaičiaus atitikimą pasirinktai prenumeratos pakopai  
- išorinės ar trečiųjų šalių prieigos prevenciją  

GuardPrompt taiko licencijuotą vartotojų limitą. Jei sukonfigūruotų vartotojų skaičius viršija licencijos pakopos leidžiamą, sistema automatiškai pereina į **Ribotą režimą**, kol problema išsprendžiama.

Organizacija turi užtikrinti, kad aktyvių vartotojų paskyrų skaičius neviršytų licencijuoto kiekio.
