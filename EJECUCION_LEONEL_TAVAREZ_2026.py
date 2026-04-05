def upload_to_drive(content_bytes, file_name, folder_id):
    service = get_drive_service()
    
    # Metadatos con la instrucción de no usar la cuota del robot
    file_metadata = {
        'name': file_name, 
        'parents': [folder_id]
    }
    
    media = MediaIoBaseUpload(BytesIO(content_bytes), mimetype='application/pdf')
    
    # Ejecución con los dos permisos necesarios
    service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id',
        supportsAllDrives=True,        # Para carpetas compartidas
        ignoreDefaultVisibility=True  # Fuerza a heredar permisos de la carpeta destino
    ).execute()
