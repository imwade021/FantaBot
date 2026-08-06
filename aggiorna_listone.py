import pandas as pd

def aggiorna_listone():
    # 1. Ecco il dizionario aggiornato con TUTTE le nuove colonne dello Scouting Report
    data = {
        'Nome': ['Sommer', 'Di Gregorio', 'Bastoni', 'Dimarco', 'Buongiorno', 'Barella', 'Koopmeiners', 'Pulisic', 'Lautaro', 'Vlahovic', 'Kvaratskhelia'],
        'Squadra': ['Inter', 'Juventus', 'Inter', 'Inter', 'Napoli', 'Inter', 'Juventus', 'Milan', 'Inter', 'Juventus', 'Napoli'],
        'R': ['P', 'P', 'D', 'D', 'D', 'C', 'C', 'C', 'A', 'A', 'A'],
        'FM': [5.8, 5.5, 6.3, 6.7, 6.2, 7.1, 7.3, 7.2, 8.5, 8.1, 7.8],
        'FVM': [45, 40, 35, 45, 30, 85, 95, 80, 180, 160, 150],
        'Qt.A': [18, 16, 15, 20, 14, 25, 28, 24, 45, 40, 38],
        'Target_Max': [50, 45, 40, 50, 35, 90, 100, 85, 190, 170, 160],
        'Slot': [1, 1, 2, 1, 2, 1, 1, 1, 1, 1, 1],
        
        # --- NUOVE METRICHE SCOUTING ---
        'Titolarita': ['Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile', 'Inamovibile'],
        'Rigori_Piazzati': ['-', '-', '-', 'Angoli/Punizioni', '-', 'Nessuno', 'Rigorista 2', 'Nessuno', 'Rigorista 1', 'Rigorista 1', 'Rigorista 1'],
        'Infortuni': ['Iron Man', 'Iron Man', 'Medio', 'Basso', 'Basso', 'Iron Man', 'Medio', 'Alto', 'Basso', 'Medio', 'Basso'],
        'Malus': ['Corretto', 'Corretto', 'Corretto', 'Corretto', 'Cartellino Facile', 'Spesso Ammonito', 'Corretto', 'Corretto', 'Spesso Ammonito', 'Spesso Ammonito', 'Corretto']
    }

    df = pd.DataFrame(data)

    # 2. Salvataggio su Excel (impostato con startrow=1 per saltare la prima riga come vuole il bot)
    try:
        with pd.ExcelWriter("listone.xlsx", engine="openpyxl") as writer:
            df.to_excel(writer, index=False, startrow=1)
        print("✅ Successo! Il file 'listone.xlsx' è stato generato con il nuovo Scouting Report.")
    except Exception as e:
        print(f"❌ Errore durante la creazione del file: {e}")

if __name__ == '__main__':
    aggiorna_listone()
