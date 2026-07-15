import streamlit as st
import pandas as pd
import numpy as np
import io

# Configuración inicial de la página
st.set_page_config(page_title="Matriz comparativa", layout="wide", page_icon="⚙️")

st.title("⚙️ Control de costos: Control Presupuestal (Real vs. Matriz)")
st.caption("Carga los archivos transaccionales y las matrices para generar el comparativo consolidado.")

# ---------------- 1. Zona de Carga de Archivos ----------------
st.subheader("Paso 1: Carga de Archivos Base")
col1, col2, col3 = st.columns(3)

with col1:
    file_real = st.file_uploader("1. Archivo Costos Reales", type=['xlsx', 'xls'])
    st.caption("Base de datos transaccional (Hoja: 'BD DATOS')")

with col2:
    file_insumos = st.file_uploader("2. Matriz de Insumos", type=['xlsx', 'xls'])
    st.caption("Presupuesto de elementos (Hoja: 'LEVANTE')")

with col3:
    file_vacunas = st.file_uploader("3. Matriz de Vacunas", type=['xlsx', 'xls'])
    st.caption("Presupuesto vacunal (Hoja: 'FACTORES')")

# Solo si los tres archivos han sido cargados, se habilita el botón de proceso
if file_real and file_insumos and file_vacunas:
    
    st.info("Archivos cargados en memoria. Listos para procesar.")
    
    if st.button("Ejecutar Cruce de Datos (ETL)", type="primary", use_container_width=True):
        
        with st.spinner('Extrayendo, normalizando y cruzando datos...'):
            try:
                # ---------------- 2. Lógica ETL (Extracción y Transformación) ----------------
                
                # A. Procesar Base de Datos Real
                df_real = pd.read_excel(file_real, sheet_name='BD DATOS')
                # Filtramos columnas clave y renombramos para estandarizar
                df_real = df_real[['Granja', 'Lote', 'Operacion', 'Material', 'Texto breve de material', '       Cantidad', '    Costo Real']]
                df_real.rename(columns={
                    'Material': 'COD SAP',
                    'Texto breve de material': 'Descripcion SAP',
                    '       Cantidad': 'Cantidad Real',
                    '    Costo Real': 'Costo Real'
                }, inplace=True)
                # Asegurar que la llave sea numérica
                df_real['COD SAP'] = pd.to_numeric(df_real['COD SAP'], errors='coerce')
                
                # B. Procesar Matriz de Insumos (Ejemplo con pestaña Levante)
                df_insumos = pd.read_excel(file_insumos, sheet_name='LEVANTE', header=4)
                df_insumos_aseo = df_insumos.iloc[1:15, 2:7].copy() # Extraer bloque específico
                df_insumos_aseo.columns = ["COD SAP", "Producto Presupuesto", "Fecha", "Unidad", "Cantidad Presupuesto"]
                df_insumos_aseo = df_insumos_aseo.dropna(subset=["Producto Presupuesto"])
                df_insumos_aseo['COD SAP'] = pd.to_numeric(df_insumos_aseo['COD SAP'], errors='coerce')
                
                # C. Procesar Matriz de Vacunas (Ejemplo pestaña Factores)
                df_vacunas_fact = pd.read_excel(file_vacunas, sheet_name='FACTORES', header=1)
                df_vac_clean = df_vacunas_fact.iloc[1:15, 0:5].copy()
                df_vac_clean.columns = ["COD SAP", "CG1", "Producto Presupuesto", "Cantidad Presupuesto", "Unidad"]
                df_vac_clean = df_vac_clean.dropna(subset=["Producto Presupuesto"])
                df_vac_clean['COD SAP'] = pd.to_numeric(df_vac_clean['COD SAP'], errors='coerce')
                
                # D. Unificar Matrices de Presupuesto (Insumos + Vacunas)
                matriz_unificada = pd.concat([
                    df_insumos_aseo[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']],
                    df_vac_clean[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']]
                ], ignore_index=True)
                
                # ---------------- 3. Cruce Relacional (Merge) ----------------
                # Unimos los costos reales con la matriz unificada usando el COD SAP
                df_cruce = pd.merge(df_real, matriz_unificada, on='COD SAP', how='left')
                
                # Rellenar vacíos en el presupuesto con 0 para cálculos numéricos
                df_cruce['Cantidad Presupuesto'] = pd.to_numeric(df_cruce['Cantidad Presupuesto'], errors='coerce').fillna(0)
                
                # ---------------- 4. Lógica de Negocio y KPIs ----------------
                df_cruce['Desviación Cantidad'] = df_cruce['Cantidad Real'] - df_cruce['Cantidad Presupuesto']
                
                # Asignación de semáforos
                condiciones = [
                    (df_cruce['Producto Presupuesto'].isna()), # No está en matriz
                    (df_cruce['Desviación Cantidad'] > 0),     # Gastó más de lo permitido
                    (df_cruce['Desviación Cantidad'] <= 0)     # Gastó igual o menos
                ]
                opciones = ['GRIS (Sin Presupuesto)', 'ROJO (Sobrecosto)', 'VERDE (Cumple)']
                df_cruce['Estado Cumplimiento'] = np.select(condiciones, opciones, default='Pendiente')
                
                # Limpieza final de columnas a mostrar
                columnas_finales = [
                    'Granja', 'Lote', 'Operacion', 'COD SAP', 'Descripcion SAP', 
                    'Cantidad Real', 'Costo Real', 'Producto Presupuesto', 
                    'Cantidad Presupuesto', 'Desviación Cantidad', 'Estado Cumplimiento'
                ]
                df_final = df_cruce[columnas_finales].sort_values(by='Desviación Cantidad', ascending=False)
                
                # Guardar en sesión
                st.session_state['df_procesado'] = df_final
                st.success("¡Datos procesados y consolidados con éxito!")

            except Exception as e:
                st.error(f"Hubo un error al ejecutar la arquitectura de datos: {str(e)}")
                st.stop()

# ---------------- 5. Visualización y Exportación ----------------
if 'df_procesado' in st.session_state:
    st.divider()
    st.subheader("📊 Vista Previa del Consolidado")
    
    df_resultado = st.session_state['df_procesado']
    
    # Aplicar colores al dataframe de previsualización
    def color_semaforo(val):
        if 'ROJO' in str(val): return 'background-color: #ffc7ce; color: #9c0006;'
        if 'VERDE' in str(val): return 'background-color: #c6efce; color: #006100;'
        if 'GRIS' in str(val): return 'background-color: #f2f2f2; color: #333333;'
        return ''
    
    st.dataframe(
        df_resultado.style.map(color_semaforo, subset=['Estado Cumplimiento']),
        use_container_width=True,
        height=400
    )
    
    # Preparar el archivo en memoria (Buffer) para evitar guardar localmente
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, index=False, sheet_name='Costo_Real_vs_Matriz')
    
    # Botón de descarga nativo de Streamlit
    st.download_button(
        label="⬇️ Descargar Reporte Final (Excel)",
        data=buffer.getvalue(),
        file_name="Reporte_Costos_Consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
