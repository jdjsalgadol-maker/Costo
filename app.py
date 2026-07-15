import streamlit as st
import pandas as pd
import numpy as np
import io

# ---------------- Configuración Inicial ----------------
st.set_page_config(page_title="Procesador de Costos Avícolas", layout="wide", page_icon="⚙️")
st.title("⚙️ Procesador ETL: Control Presupuestal (Real vs. Matriz)")
st.caption("Carga los archivos transaccionales y las matrices. El procesamiento está optimizado con Caché.")

# ---------------- Función ETL Optimizada y en Caché ----------------
# El decorador @st.cache_data evita que Excel se lea dos veces si los archivos no cambian
@st.cache_data(show_spinner=False)
def ejecutar_pipeline_etl(file_real, file_insumos, file_vacunas):
    # A. Procesar Base de Datos Real (Se leen solo las columnas necesarias para mayor velocidad)
    cols_real = ['Granja', 'Lote', 'Operacion', 'Material', 'Texto breve de material', '       Cantidad', '    Costo Real']
    df_real = pd.read_excel(file_real, sheet_name='BD DATOS', usecols=cols_real)
    df_real.rename(columns={
        'Material': 'COD SAP',
        'Texto breve de material': 'Descripcion SAP',
        '       Cantidad': 'Cantidad Real',
        '    Costo Real': 'Costo Real'
    }, inplace=True)
    df_real['COD SAP'] = pd.to_numeric(df_real['COD SAP'], errors='coerce')
    
    # B. Procesar Matriz de Insumos
    df_insumos = pd.read_excel(file_insumos, sheet_name='LEVANTE', header=4)
    df_insumos_aseo = df_insumos.iloc[1:15, 2:7].copy()
    df_insumos_aseo.columns = ["COD SAP", "Producto Presupuesto", "Fecha", "Unidad", "Cantidad Presupuesto"]
    df_insumos_aseo = df_insumos_aseo.dropna(subset=["Producto Presupuesto"])
    df_insumos_aseo['COD SAP'] = pd.to_numeric(df_insumos_aseo['COD SAP'], errors='coerce')
    
    # C. Procesar Matriz de Vacunas
    df_vacunas_fact = pd.read_excel(file_vacunas, sheet_name='FACTORES', header=1)
    df_vac_clean = df_vacunas_fact.iloc[1:15, 0:5].copy()
    df_vac_clean.columns = ["COD SAP", "CG1", "Producto Presupuesto", "Cantidad Presupuesto", "Unidad"]
    df_vac_clean = df_vac_clean.dropna(subset=["Producto Presupuesto"])
    df_vac_clean['COD SAP'] = pd.to_numeric(df_vac_clean['COD SAP'], errors='coerce')
    
    # D. Unificar Presupuesto y Cruzar con Real
    matriz_unificada = pd.concat([
        df_insumos_aseo[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']],
        df_vac_clean[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']]
    ], ignore_index=True)
    
    df_cruce = pd.merge(df_real, matriz_unificada, on='COD SAP', how='left')
    
    # ---------------- Corrección de Tipos de Datos (El error del string) ----------------
    # Forzamos que todo sea un número, y si hay texto basura, lo vuelve 0
    df_cruce['Cantidad Real'] = pd.to_numeric(df_cruce['Cantidad Real'], errors='coerce').fillna(0)
    df_cruce['Cantidad Presupuesto'] = pd.to_numeric(df_cruce['Cantidad Presupuesto'], errors='coerce').fillna(0)
    
    # Cálculo Matemático Seguro
    df_cruce['Desviación Cantidad'] = df_cruce['Cantidad Real'] - df_cruce['Cantidad Presupuesto']
    
    # E. Asignación de Semáforos
    condiciones = [
        (df_cruce['Producto Presupuesto'].isna()), # No está en matriz (Ej. Alimento)
        (df_cruce['Desviación Cantidad'] > 0),     # Gastó más de lo permitido
        (df_cruce['Desviación Cantidad'] <= 0)     # Gastó igual o menos
    ]
    opciones = ['GRIS (Sin Presupuesto)', 'ROJO (Sobrecosto)', 'VERDE (Cumple)']
    df_cruce['Estado Cumplimiento'] = np.select(condiciones, opciones, default='Pendiente')
    
    # F. Ordenar y Retornar
    columnas_finales = [
        'Granja', 'Lote', 'Operacion', 'COD SAP', 'Descripcion SAP', 
        'Cantidad Real', 'Costo Real', 'Producto Presupuesto', 
        'Cantidad Presupuesto', 'Desviación Cantidad', 'Estado Cumplimiento'
    ]
    return df_cruce[columnas_finales].sort_values(by='Desviación Cantidad', ascending=False)

# ---------------- Interfaz de Usuario ----------------
st.subheader("Paso 1: Carga de Archivos Base")
col1, col2, col3 = st.columns(3)

with col1:
    file_real = st.file_uploader("1. Archivo Costos Reales", type=['xlsx', 'xls'])
with col2:
    file_insumos = st.file_uploader("2. Matriz de Insumos", type=['xlsx', 'xls'])
with col3:
    file_vacunas = st.file_uploader("3. Matriz de Vacunas", type=['xlsx', 'xls'])

if file_real and file_insumos and file_vacunas:
    
    if st.button("🚀 Ejecutar Cruce de Datos (ETL Rápido)", type="primary", use_container_width=True):
        
        with st.spinner('Procesando datos a alta velocidad...'):
            try:
                # Llamamos a la función optimizada
                df_final = ejecutar_pipeline_etl(file_real, file_insumos, file_vacunas)
                st.session_state['df_procesado'] = df_final
                st.success("¡Datos procesados y consolidados con éxito!")
            except Exception as e:
                st.error(f"Error en el procesamiento: {str(e)}")

# ---------------- Visualización y Descarga ----------------
if 'df_procesado' in st.session_state:
    st.divider()
    st.subheader("📊 Vista Previa del Consolidado")
    
    df_resultado = st.session_state['df_procesado']
    
    def color_semaforo(val):
        if 'ROJO' in str(val): return 'background-color: #ffc7ce; color: #9c0006;'
        if 'VERDE' in str(val): return 'background-color: #c6efce; color: #006100;'
        if 'GRIS' in str(val): return 'background-color: #f2f2f2; color: #333333;'
        return ''
    
    # Mostrar tabla renderizada
    st.dataframe(
        df_resultado.style.map(color_semaforo, subset=['Estado Cumplimiento']),
        use_container_width=True,
        height=400
    )
    
    # Preparar Excel en memoria
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_resultado.to_excel(writer, index=False, sheet_name='Costo_Real_vs_Matriz')
    
    st.download_button(
        label="⬇️ Descargar Reporte Final (Excel)",
        data=buffer.getvalue(),
        file_name="Reporte_Costos_Consolidado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
