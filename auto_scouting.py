import pandas as pd

def popola_scouting_automatico():
    print("⚡ Avvio compilazione con aggiunta FASCE (Tiers)...")
    try:
        df = pd.read_excel("listone.xlsx", header=1, engine='openpyxl')
    except Exception as e:
        print(f"❌ Errore: {e}")
        return

    df['FVM'] = pd.to_numeric(df['FVM'], errors='coerce').fillna(1)
    df['Qt.A'] = pd.to_numeric(df['Qt.A'], errors='coerce').fillna(1)
    
    fascia_list, titolarita_list, rigori_list, infortuni_list, malus_list = [], [], [], [], []

    for _, row in df.iterrows():
        fvm = row['FVM']
        ruolo = str(row.get('R', '')).upper()
        nome = str(row.get('Nome', ''))

        # NUOVO: 0. LOGICA FASCE (TIERS)
        if fvm >= 200: fsc = "🔥 1° Fascia (Top Player)"
        elif fvm >= 100: fsc = "💎 2° Fascia (Semi-Top)"
        elif fvm >= 40: fsc = "🛡️ 3° Fascia (Titolare Solido)"
        elif fvm >= 15: fsc = "⚙️ 4° Fascia (Alternativa/Scommessa)"
        else: fsc = "🚑 5° Fascia (Riserva)"
        fascia_list.append(fsc)

        # 1. TITOLARITÀ
        if fvm >= 150: tit = "Inamovibile (90%+)"
        elif fvm >= 50: tit = "Titolare (75%+)"
        elif fvm >= 15: tit = "Ballottaggio / Co-Titolare"
        elif fvm >= 5: tit = "Rincalzo / Copertura"
        else: tit = "Riserva"
        titolarita_list.append(tit)

        # 2. RIGORI
        if any(top_rig in nome.upper() for top_rig in ['CALHANOGLU', 'DYBALA', 'LAUTARO', 'LOOKMAN', 'ORSOLINI', 'ZAPATA', 'GUDMUNDSSON', 'KVARATSKHELIA', 'ZACCAGNI', 'PULISIC', 'BERARDI', 'KEAN', 'LUKAKU']):
            rig = "1° Rigorista / Punizioni"
        elif ruolo in ['A', 'C'] and fvm >= 180: rig = "Possibile Rigorista / Piazzati"
        elif ruolo in ['A', 'C'] and fvm >= 60: rig = "Vice-Rigorista / Angoli"
        else: rig = "No Rigori / Saltuario"
        rigori_list.append(rig)

        # 3. INFORTUNI
        if any(fragile in nome.upper() for fragile in ['DYBALA', 'BERARDI', 'SANCHES', 'SENSI', 'PELLEGRINI', 'ZAPATA']):
            inf = "Storico Infortuni Elevato ⚠️"
        elif fvm >= 100: inf = "Sano (Monitorato)"
        else: inf = "Integro / Buona tenuta"
        infortuni_list.append(inf)

        # 4. MALUS
        if ruolo == 'D' and fvm < 20: mal = "Tendenza al giallo 🟨"
        elif ruolo == 'C' and fvm < 15: mal = "Rischio Malus Frequente 🟨"
        else: mal = "Malus nella norma"
        malus_list.append(mal)

    df['Fascia'] = fascia_list
    df['Titolarita'] = titolarita_list
    df['Rigori_Piazzati'] = rigori_list
    df['Infortuni'] = infortuni_list
    df['Malus'] = malus_list

    with pd.ExcelWriter("listone.xlsx", engine="openpyxl") as writer:
        df.to_excel(writer, index=False, startrow=1)
    print("✅ COMPILAZIONE COMPLETATA! (Fasce aggiunte)")

if __name__ == '__main__':
    popola_scouting_automatico()
