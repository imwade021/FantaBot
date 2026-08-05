import os
import pandas as pd

def ottieni_dati_aggiornati():
    print("⏳ Sincronizzazione ed elaborazione listone locale in corso...")
    
    file_path = "listone.xlsx"
    if not os.path.exists(file_path):
        print("❌ File listone.xlsx non trovato nella cartella del progetto!")
        return

    # Lettura Excel da riga 2 (header=1)
    df = pd.read_excel(file_path, header=1, engine='openpyxl')

    # 1. Calcolo Fantamedia (FM) stimata
    def estrai_fm(row):
        fvm = float(row.get('FVM', 0)) if pd.notnull(row.get('FVM')) else 0
        r = str(row.get('R', 'C')).upper()
        base = 7.0 if r == 'A' else (6.4 if r == 'C' else (6.1 if r == 'D' else 5.5))
        return round(base + (fvm / 150.0), 2)

    # 2. Calcolo Slot Consigliato
    def calcola_slot(row):
        fvm = float(row.get('FVM', 0)) if pd.notnull(row.get('FVM')) else 0
        r = str(row.get('R', 'C')).upper()
        if r == 'A':
            return "1° Slot Top" if fvm >= 220 else ("1° Slot" if fvm >= 120 else ("2° Slot" if fvm >= 60 else "3° Slot/Scommessa"))
        elif r == 'C':
            return "1° Slot Top" if fvm >= 120 else ("1° Slot" if fvm >= 70 else ("2° Slot" if fvm >= 35 else "3° Slot"))
        elif r == 'D':
            return "1° Slot Top" if fvm >= 60 else ("1° Slot" if fvm >= 35 else ("2° Slot" if fvm >= 18 else "3° Slot"))
        else:
            return "1° Slot" if fvm >= 40 else ("2° Slot" if fvm >= 20 else "3° Slot")

    # 3. Calcolo Target Max Budget
    def calcola_target(row):
        fvm = float(row.get('FVM', 0)) if pd.notnull(row.get('FVM')) else 0
        qta = float(row.get('Qt.A', 0)) if pd.notnull(row.get('Qt.A')) else 0
        return max(int(qta), int(round(fvm * 0.42)))

    # Database Rigoristi di riferimento
    rigoristi_top = [
        "LAUTARO", "VLAHOVIC", "ORSOLINI", "CALHANOGLU", "DYBALA", 
        "KOOPMEINERS", "PULISIC", "ZAPATA", "MCTOMINAY", "LOOKMAN", "RETUGUI"
    ]

    # Popolamento nuove colonne
    df['FM'] = df.apply(estrai_fm, axis=1)
    df['Slot'] = df.apply(calcola_slot, axis=1)
    df['Target_Max'] = df.apply(calcola_target, axis=1)
    df['Rigorista'] = df['Nome'].apply(lambda n: "Sì" if any(rig in str(n).upper() for rig in rigoristi_top) else "No")
    df['Note'] = df.apply(lambda r: f"Puntare max {r['Target_Max']} cr. ({r['Slot']})", axis=1)

    # Scrittura su file Excel
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Listone', startrow=1)

    print("🚀 listone.xlsx arricchito con successo ed esente da errori!")

if __name__ == '__main__':
    ottieni_dati_aggiornati()
