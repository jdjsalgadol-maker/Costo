import streamlit as st
import pandas as pd
import numpy as np
import io
import plotly.express as px

# ---------------- Configuración Inicial ----------------
st.set_page_config(page_title="Dashboard Control de Costos", layout="wide", page_icon="📈")

# ---------------- Función ETL Optimizada y Financiera ----------------
@st.cache_data(show_spinner=False)
def ejecutar_pipeline_etl(file_real, file_insumos, file_vacunas):
    # A. Procesar Base de Datos Real
    cols_real = ['Granja', 'Lote', 'Operacion', 'Material', 'Texto breve de material', '       Cantidad', '    Costo Real']
    df_real = pd.read_excel(file_real, sheet_name='BD DATOS', usecols=cols_real)
    
    # Aquí se corrige el KeyError limpiando los nombres exactos de las columnas
    df_real.rename(columns={
        'Material': 'COD SAP',
        'Texto breve de material': 'Descripcion SAP',
        '       Cantidad': 'Cantidad Real',
        '    Costo Real': 'Costo Real'
    }, inplace=True)
    
    # Filtro de limpieza corporativa en la base de datos
    for col in ['Granja', 'Operacion', 'Descripcion SAP']:
        if col in df_real.columns:
            df_real = df_real[~df_real[col].astype(str).str.contains('avidesa de occidente', case=False, na=False)]

    df_real['COD SAP'] = pd.to_numeric(df_real['COD SAP'], errors='coerce')
    
    # B. Procesar Matrices
    df_insumos = pd.read_excel(file_insumos, sheet_name='LEVANTE', header=4).iloc[1:15, 2:7].copy()
    df_insumos.columns = ["COD SAP", "Producto Presupuesto", "Fecha", "Unidad", "Cantidad Presupuesto"]
    
    df_vacunas = pd.read_excel(file_vacunas, sheet_name='FACTORES', header=1).iloc[1:15, 0:5].copy()
    df_vacunas.columns = ["COD SAP", "CG1", "Producto Presupuesto", "Cantidad Presupuesto", "Unidad"]
    
    matriz_unificada = pd.concat([
        df_insumos[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']],
        df_vacunas[['COD SAP', 'Producto Presupuesto', 'Cantidad Presupuesto']]
    ], ignore_index=True).dropna(subset=["Producto Presupuesto"])
    
    matriz_unificada['COD SAP'] = pd.to_numeric(matriz_unificada['COD SAP'], errors='coerce')
    
    # C. Cruce de Datos
    df_cruce = pd.merge(df_real, matriz_unificada, on='COD SAP', how='left')
    
    # Limpieza numérica segura para cálculos
    df_cruce['Cantidad Real'] = pd.to_numeric(df_cruce['Cantidad Real'], errors='coerce').fillna(0)
    df_cruce['Costo Real'] = pd.to_numeric(df_cruce['Costo Real'], errors='coerce').fillna(0)
    df_cruce['Cantidad Presupuesto'] = pd.to_numeric(df_cruce['Cantidad Presupuesto'], errors='coerce').fillna(0)
    
    # D. Lógica Financiera y KPIs
    df_cruce['Desviación Cantidad'] = df_cruce['Cantidad Real'] - df_cruce['Cantidad Presupuesto']
    
    # Estimación de costo presupuestado en dinero para el Dashboard
    df_cruce['Costo Unitario'] = np.where(df_cruce['Cantidad Real'] > 0, df_cruce['Costo Real'] / df_cruce['Cantidad Real'], 0)
    df_cruce['Costo Presupuestado'] = df_cruce['Cantidad Presupuesto'] * df_cruce['Costo Unitario']
    df_cruce['Variación Financiera'] = df_cruce['Costo Real'] - df_cruce['Costo Presupuestado']
    
    # Semáforos
    condiciones = [
        (df_cruce['Producto Presupuesto'].isna()), 
        (df_cruce['Desviación Cantidad'] > 0),     
        (df_cruce['Desviación Cantidad'] <= 0)     
    ]
    df_cruce['Estado'] = np.select(condiciones, ['GRIS (Sin Presupuesto)', '🔴 ROJO (Sobrecosto)', '🟢 VERDE (Cumple)'], default='Pendiente')
    
    return df_cruce

# ---------------- UI: Encabezado y Carga ----------------
st.title("📊 Dashboard de Control de Costos")
st.markdown("Análisis interactivo de ejecución presupuestal vs. gasto real.")

with st.expander("📁 1. Cargar Bases de Datos (ETL)", expanded=not 'df_procesado' in st.session_state):
    col1, col2, col3 = st.columns(3)
    with col1: file_real = st.file_uploader("Archivo Costos Reales", type=['xlsx', 'xls'])
    with col2: file_insumos = st.file_uploader("Matriz Insumos", type=['xlsx', 'xls'])
    with col3: file_vacunas = st.file_uploader("Matriz Vacunas", type=['xlsx', 'xls'])
    
    if file_real and file_insumos and file_vacunas:
        if st.button("🚀 Procesar Modelo de Datos", type="primary", use_container_width=True):
            with st.spinner('Construyendo modelo relacional y tableros...'):
                try:
                    st.session_state['df_procesado'] = ejecutar_pipeline_etl(file_real, file_insumos, file_vacunas)
                    st.success("¡Datos procesados exitosamente!")
                except Exception as e:
                    st.error(f"Error procesando los datos: {e}")

# ---------------- UI: Dashboard Interactivo ----------------
if 'df_procesado' in st.session_state:
    df = st.session_state['df_procesado']
    
    # --- PANEL LATERAL DE FILTROS ---
    st.sidebar.header("Filtros de Análisis")
    
    lista_granjas = df['Granja'].dropna().unique().tolist()
    filtro_granja = st.sidebar.multiselect("📍 Granja", lista_granjas, default=lista_granjas[:3] if len(lista_granjas)>3 else lista_granjas)
    
    lista_estados = df['Estado'].dropna().unique().tolist()
    filtro_estado = st.sidebar.multiselect("🚦 Estado de Cumplimiento", lista_estados, default=lista_estados)
    
    # Aplicar filtros
    df_filtrado = df[(df['Granja'].isin(filtro_granja)) & (df['Estado'].isin(filtro_estado))]
    
    if df_filtrado.empty:
        st.warning("No hay datos para mostrar con los filtros seleccionados.")
    else:
        # --- SECCIÓN DE KPIs ---
        st.markdown("### Indicadores Globales")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        total_real = df_filtrado['Costo Real'].sum()
        total_presupuesto = df_filtrado['Costo Presupuestado'].sum()
        desviacion_total = total_real - total_presupuesto
        pct_cumplimiento = (total_real / total_presupuesto - 1) * 100 if total_presupuesto > 0 else 0
        
        kpi1.metric("Gasto Real Total", f"${total_real:,.0f}")
        kpi2.metric("Presupuesto Total", f"${total_presupuesto:,.0f}")
        kpi3.metric("Sobrecosto / Ahorro", f"${desviacion_total:,.0f}", delta=f"{pct_cumplimiento:+.1f}%", delta_color="inverse")
        kpi4.metric("Insumos Evaluados", f"{len(df_filtrado)} registros")

        st.divider()

        # --- SECCIÓN DE GRÁFICOS (PLOTLY) ---
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("#### Ejecución por Granja")
            df_agrupado = df_filtrado.groupby('Granja')[['Costo Real', 'Costo Presupuestado']].sum().reset_index()
            fig_bar = px.bar(df_agrupado, x='Granja', y=['Costo Presupuestado', 'Costo Real'], 
                             barmode='group', 
                             color_discrete_map={'Costo Presupuestado': '#2ca02c', 'Costo Real': '#1f77b4'},
                             labels={'value': 'Costo ($)', 'variable': 'Métrica'})
            fig_bar.update_layout(margin=dict(l=0, r=0, t=30, b=0), legend_title_text='')
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_chart2:
            st.markdown("#### Top Mayores Desviaciones (Sobrecostos)")
            df_sobrecostos = df_filtrado[df_filtrado['Variación Financiera'] > 0]
            if not df_sobrecostos.empty:
                top_desviaciones = df_sobrecostos.groupby('Descripcion SAP')['Variación Financiera'].sum().nlargest(10).reset_index()
                fig_bar_h = px.bar(top_desviaciones, y='Descripcion SAP', x='Variación Financiera', 
                                   orientation='h', color='Variación Financiera', color_continuous_scale='Reds')
                fig_bar_h.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig_bar_h, use_container_width=True)
            else:
                st.info("No hay desviaciones negativas (sobrecostos) en esta selección.")

        # --- SECCIÓN DE DETALLE DE DATOS ---
        st.markdown("#### Auditoría Detallada de Insumos")
        
        columnas_mostrar = ['Granja', 'Operacion', 'COD SAP', 'Descripcion SAP', 'Cantidad Real', 'Cantidad Presupuesto', 'Costo Real', 'Estado']
        df_display = df_filtrado[columnas_mostrar].sort_values(by='Costo Real', ascending=False)
        
        def estilo_filas(row):
            color = 'background-color: #ffc7ce; color: #9c0006' if 'ROJO' in str(row['Estado']) else \
                    'background-color: #c6efce; color: #006100' if 'VERDE' in str(row['Estado']) else ''
            return [color] * len(row)
            
        st.dataframe(df_display.style.apply(estilo_filas, axis=1).format({'Costo Real': '${:,.0f}'}), use_container_width=True, height=300)
        
        # Exportación
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_display.to_excel(writer, index=False, sheet_name='Reporte_Financiero')
        
        st.download_button("⬇️ Descargar Reporte Gerencial (Excel)", data=buffer.getvalue(), 
                           file_name="Dashboard_Costos_Filtrado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
