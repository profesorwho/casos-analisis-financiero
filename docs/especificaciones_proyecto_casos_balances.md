# Especificaciones del proyecto: Generador de casos para curso de análisis de balances

**Documento vivo.** Se actualiza a cada decisión de diseño relevante. Ver historial de cambios al final.

Última actualización: Sesión de diseño inicial (Fase 0-1, pre-construcción).

---

## 1. Objetivo del proyecto

Construir una herramienta que genere automáticamente, bajo demanda ("pulsando un botón"), casos empresariales ficticios pero financieramente realistas y coherentes, para un curso profesional de análisis económico-financiero de cuentas anuales españolas (PGC).

Cada caso generado debe:
- Estar construido desde un **modelo económico interno coherente** (no datos aleatorios sueltos): ventas → márgenes → resultado → circulante → NOF → inversión → financiación → deuda → intereses → resultado neto → generación de caja → patrimonio neto.
- Cuadrar contablemente en todos sus estados (balance, PyG, ECPN, EFE).
- Incluir pistas analíticas en la memoria que permitan al alumno descubrir riesgos no evidentes a simple vista.
- Servir para trabajar 7 sesiones de curso, con casuística didáctica variada y progresiva.

## 2. Alcance funcional (heredado del prompt original del formador)

### 2.1. Empresas base a generar por caso

> **⚠️ SUPERADO.** La restricción de que solo existan "Empresa A" (PYME industrial/manufacturera) y "Empresa B" (grande, industrial/servicios industriales) queda superada por la evolución del proyecto hacia un banco extenso de casos combinables (ver secciones 2.12 y 2.22). El generador debe poder producir empresas de **cualquiera de los 27 sectores del catálogo** (sección 2.22), en modelo abreviado o normal según el tamaño resultante, no solo de los dos sectores originales. Se mantiene como referencia histórica del planteamiento inicial:

- **Empresa A** (planteamiento inicial, ya superado): PYME española, modelo abreviado, sector industrial/manufacturero. Activo 3-4M€, cifra de negocio 6-8M€, 30-50 empleados.
- **Empresa B** (planteamiento inicial, ya superado): empresa mayor, modelo normal, sector industrial/servicios industriales. Por encima de los umbrales del modelo abreviado, +100 empleados.
- **Se mantiene sin cambios**: histórico interno de 3 años (2023-2025); los estados oficiales muestran 2024-2025, 2023 queda para análisis interno de tendencia. Se mantiene también la lógica de generar habitualmente una pareja de empresas conectable por caso (sección 2.14), aunque ya no estén ancladas a un sector fijo cada una.

### 2.2. Estados financieros requeridos por empresa
Balance, cuenta de pérdidas y ganancias, ECPN, EFE (cuando corresponda), memoria — siguiendo modelos oficiales del PGC (abreviado para A, normal para B).

### 2.3. Situaciones económicas a representar
**Empresa A** (PYME): crecimiento de ventas, aumento de existencias y clientes, tensión de cobro, caída de caja, incremento de deuda, necesidad de refinanciación, concentración de clientes, inversión en maquinaria, posible obsolescencia de stock, resultado positivo pero cash flow insuficiente para financiar toda la inversión. El caso debe admitir tanto lectura optimista como prudente.

**Empresa B** (grande): fuerte crecimiento, adquisición de unidad de negocio, incremento de inmovilizado, activo mantenido para la venta, deuda bancaria LP/CP, financiación intragrupo, activos/pasivos fiscales diferidos, instrumentos financieros y cobertura de tipos, subvenciones, posible operación extraordinaria, ventas creciendo más que clientes, tensión de caja pese a mejora de resultado. Parte de la mejora 2024-2025 debe poder no ser recurrente.

### 2.4. Memoria con pistas analíticas
La memoria debe incluir información cualitativa útil (actividad, criterios contables, inmovilizado, existencias, clientes, deuda, vencimientos, operaciones vinculadas, impuestos, contingencias, subvenciones, hechos posteriores, etc.) con pistas del tipo "3 clientes = 55% de ventas", "renegociación bancaria en curso", "deuda relevante vence en 12 meses", etc. **No todas las pistas en el mismo caso** — deben variar entre casos generados para que el alumno tenga que descubrirlas cada vez.

### 2.5. Consistencia contable (crítico)
- ACTIVO = PATRIMONIO NETO + PASIVO en todos los casos.
- Resultado de PyG conectado correctamente con patrimonio neto.
- EFE reconciliado: efectivo inicial +/- variación neta = efectivo final.
- Movimientos de deuda, inmovilizado, impuestos y dividendos coherentes entre sí y con el balance.
- Debe existir una función/proceso de validación automática (`validate_company()` o equivalente) que impida generar o publicar un caso que no cuadre.

### 2.6. Datos de apoyo por caso
Ventas por línea de negocio, clientes y concentración, aging de clientes, inventario por categoría, vencimientos de deuda, capex, plantilla, gastos operativos, tipos de interés, calendario de amortización de deuda.

### 2.7. Casuística didáctica (banco de situaciones a combinar) — listado completo
Estas 22 situaciones son la base de lo que en el proyecto llamamos **"arquetipos"** (ver sección 4):

1. Crecimiento con destrucción de caja.
2. Beneficio sin suficiente cash flow.
3. Aumento de NOF.
4. Deterioro del ciclo de caja.
5. Exceso de stock.
6. Aumento de clientes.
7. Dependencia de pocos clientes.
8. Refinanciación.
9. Apalancamiento.
10. Mejora de EBITDA.
11. Mejora de margen.
12. Resultado extraordinario.
13. Diferencias entre EBITDA, EBIT, beneficio y caja.
14. ROE elevado por apalancamiento.
15. Riesgo de liquidez pese a beneficio.
16. Riesgo de refinanciación.
17. Capex elevado.
18. Adquisición.
19. Activo mantenido para la venta.
20. Operaciones vinculadas.
21. Coberturas.
22. Información relevante en memoria.

Ejemplos de pistas analíticas que puede contener la memoria (no todas a la vez en un mismo caso):
- 3 clientes representan el 55% de ventas.
- Parte de los clientes presenta retrasos.
- Una parte del inventario tiene baja rotación.
- Existe una renegociación bancaria.
- Una deuda importante vence en los próximos 12 meses.
- Una adquisición explica una parte relevante del crecimiento.
- Existe un activo que se pretende vender.
- Hay una cobertura de tipos de interés.
- Existe una contingencia potencial.

### 2.8. Incidencias didácticas opcionales
Entre 5 y 10 incidencias activables por el formador para ejercicios avanzados. **No deben contaminar los estados base** — se activan aparte. Ejemplos dados por el formador:
- Clasificación incorrecta de deuda (corriente/no corriente).
- Gasto capitalizado incorrectamente.
- Cliente deteriorado no provisionado.
- Stock obsoleto no reconocido.
- Gasto extraordinario mezclado con recurrente.
- Error en clasificación corriente/no corriente (otros casos distintos al de deuda).
- Operación vinculada no identificada correctamente.

### 2.9. Versiones del material
- **Versión alumno**: datos, cuentas, memoria, análisis, dashboard vacío o parcial, sin diagnóstico resuelto.
- **Versión formador**: incluye solución, hipótesis, ratios esperados, red flags, recomendaciones, explicación de cada incidencia.
- Tabla de relación entre cada situación didáctica y las 7 sesiones del curso.

### 2.10. Salidas del sistema (contenido, no formato final — ver sección 4 sobre arquitectura)
Estados financieros completos, análisis horizontal y vertical, FM y NOF, periodo de maduración, ratios de deuda y rentabilidad, punto muerto, dashboard visual con semáforos y red flags (sin umbrales rígidos universales — deben interpretarse con tendencia/sector/modelo de negocio), hoja/vista de diagnóstico (HECHO → CÁLCULO → HIPÓTESIS → EVIDENCIA NECESARIA → IMPACTO → PRIORIDAD → RECOMENDACIÓN), controles automáticos de cuadre.

**Métricas obligatorias del dashboard:** ventas, EBITDA, EBIT, beneficio neto, caja, deuda, deuda/EBITDA, cobertura de intereses, FM, NOF, ciclo de caja, ROA, ROE, margen operativo, margen neto — con evolución, semáforos y tendencias, y una advertencia visible de que los ratios deben interpretarse con tendencia/sector/modelo de negocio/estructura financiera/calidad del resultado, no contra umbrales universales.

**Validaciones que deben bloquear/marcar como error la generación de un caso:**
- El balance no cuadra (Activo ≠ PN + Pasivo).
- El EFE no reconcilia (efectivo inicial +/- variación ≠ efectivo final).
- El patrimonio neto no evoluciona de forma coherente con el resultado y los movimientos declarados.
- Existen referencias imposibles entre hojas/datos.
- Existen valores absurdos (p. ej. negativos donde no proceden, magnitudes fuera de rango razonable).
- Los datos de origen (auxiliares) no coinciden con los estados financieros derivados.

### 2.11. Especificación técnica y estructura originales del prompt (documentadas como referencia, pendientes de adaptar a la arquitectura decidida en la sección 4)

Estas especificaciones formaban parte del planteamiento original, pensado inicialmente como un único script Python que generaba un Excel. Se mantienen documentadas íntegramente porque contienen requisitos de contenido/funcionalidad que siguen aplicando independientemente del formato final (Excel, app web, o ambos) — lo que puede cambiar es *cómo* se implementan, no *qué* deben producir.

**Stack técnico preferido originalmente:** Python, con pandas, numpy, openpyxl, pathlib, y dataclasses cuando resulte útil. *(Nota: al mover la construcción a Claude Code y posiblemente a una app web, este stack puede ampliarse — p. ej. con un backend/frontend web — pero el motor de datos en Python/pandas sigue siendo válido como núcleo.)*

**Checklist funcional que debía cubrir el script (16 pasos):**
1. Crear los datos.
2. Validar los estados.
3. Crear Excel.
4. Crear las hojas de cuentas anuales.
5. Crear hojas de datos auxiliares.
6. Crear análisis horizontal.
7. Crear análisis vertical.
8. Crear FM.
9. Crear NOF.
10. Crear periodo de maduración.
11. Crear ratios de deuda.
12. Crear ratios de rentabilidad.
13. Crear punto muerto.
14. Crear dashboard.
15. Crear diagnóstico.
16. Crear controles automáticos.

**Estructura de pestañas del Excel original (24 hojas), como referencia de contenido mínimo a cubrir sea cual sea el formato final:**
`00_Guia`, `01_Datos`, `02_Balance_Abreviado`, `03_PyG_Abreviada`, `04_ECPN`, `05_EFE`, `06_Memoria`, `07_Balance_Normal`, `08_PyG_Normal`, `09_ECPN_Normal`, `10_EFE_Normal`, `11_Memoria_Normal`, `12_Horizontal`, `13_Vertical`, `14_FM_NOF`, `15_Maduracion`, `16_Deuda`, `17_Rentabilidad`, `18_Punto_Muerto`, `19_Dashboard`, `20_Diagnostico`, `21_Controles`, `22_Datos_Auxiliares`, `23_Incidencias_Didacticas`.

**Entregables originales del proyecto:**
1. Script Python completo.
2. Excel generado.
3. CSV de datos base.
4. JSON con hipótesis del caso.
5. Documento README explicando el caso.
6. Documento separado con las soluciones/interpretaciones esperadas para el formador.

*(Nota: con la arquitectura de repositorio de casos + app web, estos entregables pueden traducirse a: motor de generación con tests, exportador Excel opcional, base de datos/JSON de casos, documentación de cada caso accesible desde la propia app, y vista de soluciones integrada para el formador en vez de documento aparte. A decidir en Fase 5-6.)*

## 2.12. Combinación de arquetipos en un mismo caso

Funcionalidad decidida: un caso debe poder generarse combinando **varios arquetipos a la vez** (no solo uno), para representar situaciones realistas donde conviven varios fenómenos económicos, y para dar progresión de dificultad entre las 7 sesiones (pocos arquetipos al principio, varios entrelazados al final).

**Requisitos de diseño para que esto sea seguro y didácticamente útil:**

- **Cada arquetipo se define como un módulo parametrizable**, no como una plantilla de caso cerrada: aplica ajustes sobre las variables del modelo económico interno (NOF, márgenes, deuda, caja, PN, etc.), de forma que varios arquetipos puedan aplicarse a la vez sobre el mismo modelo.
- **Intensidad variable por arquetipo** (p. ej. leve/moderado/fuerte, o escala numérica): cada arquetipo activo se aplica con un factor de intensidad, no solo on/off.
- **Matriz de compatibilidad entre arquetipos**: se definen qué combinaciones son conflictivas o económicamente contradictorias. Si el usuario selecciona una combinación incompatible en la interfaz de generación, debe mostrarse una **alerta de peligro y requerir doble confirmación** antes de generar el caso.
- **Modelo de complejidad real (no un simple conteo de arquetipos activos).** Se ha detectado que el número de arquetipos combinados NO es un buen indicador de la dificultad real del caso: dos arquetipos que se solapan mucho pueden ser más complejos de analizar que cuatro que apenas interactúan. La puntuación de complejidad debe calcularse a partir de:
  - **Solapamiento**: cuántas variables económicas tocan en común los arquetipos activos (a mayor solapamiento, mayor complejidad).
  - **Contradicción direccional**: si arquetipos activos empujan la misma variable en sentidos opuestos, esto suma complejidad de forma no lineal (no se cancela simplemente).
  - **Dispersión entre estados financieros**: cuántos estados distintos (balance, PyG, EFE, memoria) hay que cruzar para desenredar el caso.
  - La intensidad de cada arquetipo pondera esta puntuación (mismo solapamiento con intensidades altas = más complejidad).
  - Cuando la puntuación supere un umbral, la interfaz debe avisar de que el caso presenta complejidad elevada / riesgo de ser poco legible para el alumno, independientemente de cuántos arquetipos se hayan seleccionado.
- **Validador contable reforzado para combinaciones.** El validador de cuadre (sección 2.5/2.10) debe robustecerse para detectar descuadres e incoherencias que solo aparecen cuando varias fuerzas económicas actúan a la vez sobre el modelo (efectos de segundo orden: p. ej. más deuda → más intereses → menos resultado → menos caja generada → afecta a NOF).
- **Revisión de coherencia interna de las pistas de memoria al combinar arquetipos.** Cuando se combinan varios arquetipos, sus pistas de memoria asociadas no deben contradecirse entre sí (p. ej. no declarar "sin contingencias relevantes" si hay un arquetipo de contingencia activo). Enfoque propuesto: cada pista lleva etiquetas de las variables/temas que toca; se aplican reglas explícitas para detectar y resolver contradicciones antes de redactar la memoria final; un LLM puede usarse como revisor de redacción final, pero no como responsable de la lógica de coherencia.

### 2.13. Validación de plausibilidad sectorial (además del cuadre contable)

Confirmado como requisito. Más allá de validar que los estados cuadran internamente (sección 2.5/2.10), el sistema debe incluir un **segundo nivel de validación** que compruebe si los ratios resultantes de un caso son creíbles para su sector, contrastándolos contra el catálogo de ratios sectoriales de la Fase 1 (ACCID). No basta con la consistencia interna: el caso también debe ser verosímil externamente (que ningún analista real lo considere absurdo para ese sector y tamaño de empresa).

### 2.14. Relación entre Empresa A y Empresa B por tanda de generación

Confirmado como requisito. Al generar una tanda (Empresa A + Empresa B), el sistema debe permitir que ambas empresas estén, opcionalmente, **narrativamente conectadas** (p. ej. relación cliente-proveedor, sectores relacionados, una es antigua unidad de la otra), además del modo por defecto en que son completamente independientes. Esto habilita ejercicios de comparación cruzada entre ambas empresas.

### 2.15. Trazabilidad y reproducibilidad de cada caso

Confirmado como requisito. Cada caso generado debe guardar sus **metadatos de generación**: arquetipos activos, intensidad de cada uno, semilla aleatoria usada, versión del catálogo de ratios sectoriales, y versión normativa (PGC) de referencia. Esto permite: regenerar exactamente el mismo caso si es necesario, defender un caso concreto ante una duda de un alumno, y detectar si un caso ha quedado desactualizado tras un cambio normativo o una actualización del catálogo de ratios.

### 2.16. Variantes de examen / control de copia

Confirmado como requisito. El sistema debe poder generar **varias variantes de un mismo caso**: misma combinación de arquetipos y misma intensidad/dificultad, pero con cifras y nombres distintos entre variantes. Pensado para uso en evaluación, dando a cada alumno una variante distinta del mismo ejercicio y evitando copia entre ellos.

### 2.17. Nombres ficticios sin parecido con empresas reales

Confirmado como requisito. El sistema debe incluir un generador o catálogo de nombres de empresa y denominaciones sectoriales lo bastante genéricos como para evitar parecidos razonables con empresas españolas reales existentes.

### 2.18. Mantenimiento del catálogo de ratios sectoriales

Confirmado como requisito de proceso (no solo de software). El catálogo de ratios (Fase 1, fuente ACCID) no se considera estático: debe preverse un proceso, aunque sea manual, para **refrescarlo anualmente** con cada nueva edición del informe, de forma que los casos generados no queden anclados permanentemente a los datos de un único año.

### 2.19. Rúbrica de corrección del diagnóstico

Confirmado como requisito. La ficha de diagnóstico del formador (HECHO/CÁLCULO/HIPÓTESIS/EVIDENCIA NECESARIA/IMPACTO/PRIORIDAD/RECOMENDACIÓN — sección 2.10) debe llevar asociada una **rúbrica de puntuación**, para que los casos generados puedan usarse también como evaluación calificable, no solo como ejercicio de clase sin nota.

### 2.20. Control de diversidad en el repositorio de casos

Confirmado como requisito. A medida que el repositorio de casos crece, el sistema debe incluir un chequeo que **evite generar casos excesivamente parecidos entre sí** sin que el formador se dé cuenta, comparando los nuevos casos contra los ya existentes en el repositorio (combinación de arquetipos, intensidades y cifras resultantes).

### 2.21. Acceso del alumno a los datos sectoriales de referencia

Confirmado como requisito, tras descartar una versión más compleja con hipótesis previa obligatoria (ver historial de cambios v0.6 — se valoró como una mecánica que alargaba excesivamente la resolución del caso, cuando lo natural es que el alumno consulte solo los ratios de los que sospeche algo).

Mecánica final, simple:
- El catálogo de ratios sectoriales (Fase 1, fuente ACCID) está disponible como **consulta activa**, no expuesto por defecto junto a cada ratio calculado en el dashboard o los estados. El alumno accede a él cuando lo considera oportuno, igual que un profesional consultaría la Central de Balances o el informe ACCID ante un ratio que le genera dudas.
- Cuando se consulta, el dato se muestra como **rango por cuartiles**, no como media puntual — se mantiene este punto porque no añade fricción relevante y sí mejora la calidad del contraste (obliga a razonar posición relativa dentro de un rango, no una comparación binaria con un número único).
- No hay exigencia de formular hipótesis previa, ni bloqueo, ni feedback de acierto/error asociado a esta consulta.

### 2.22. Catálogo de sectores del banco extendido (27 sectores)

Confirmado como requisito. Sustituye el planteamiento original de dos sectores fijos (sección 2.1) por un catálogo de **27 sectores**, seleccionados para representar de forma realista la composición de la economía vasca (no solo el tejido industrial), con datos de ratios reales extraídos del informe ACCID "Ratios Sectoriales 2024" (ver Fase 1, sección "Log de flujo de trabajo").

**Criterio de selección seguido:**
1. Partida inicial centrada en industria/servicios industriales relevantes en Euskadi (clústeres oficiales del Gobierno Vasco, peso en VAB/empleo según Eustat).
2. Corrección tras detectar sobrerrepresentación del sector metal: análisis de similitud estadística entre sectores (clustering jerárquico sobre 7 ratios normalizados) para identificar y eliminar redundancia real, no solo aparente.
3. Ampliación a bloques ausentes tras contrastar con datos reales de composición de la economía vasca por número de establecimientos y empleo (Eustat, DIRAE 2024): comercio/transporte/hostelería (34,8% de establecimientos, el mayor bloque), administración/educación/sanidad (12,3%/24,6% empleo), construcción (11,6%).
4. Recorte final de redundancia industrial (de 13 a 9 sectores industriales) para equilibrar el peso relativo del catálogo con el peso real de cada bloque en la economía vasca.

**Catálogo final (27 sectores), por bloque:**

*Industria (9):* Siderurgia (24.1) · Automoción (29) · Carne y productos cárnicos (10.1) · Química básica (20.1) · Maquinaria y equipo (28) · Aeroespacial (30.3) · Ferroviario (30.2) · Refino de petróleo (19) · Energía eléctrica (35.1)

*Servicios industriales (4):* Reparación de maquinaria (33.1) · Instalación industrial (33.2) · Ingeniería técnica (71) · Investigación y desarrollo (72)

*Servicios profesionales / TIC (3):* Contabilidad y auditoría (69.2) · Consultoría de gestión (70.2) · TIC (62)

*Transporte y logística (2):* Almacenamiento (52) · Transporte de mercancía por carretera (4941)

*Comercio y hostelería (4):* Comercio al por menor / supermercados (47.1) · Comercio al por mayor (46) · Restaurantes (56.1) · Hoteles (55.1)

*Construcción (2):* Construcción de edificios (41.2) · Instalaciones eléctricas y de fontanería en obras (43.2)

*Administración, educación y sanidad (2):* Educación (85) · Actividades hospitalarias (86.1)

*Inmobiliario (1):* Actividades inmobiliarias (68)

**Datos disponibles por sector:** ver sección 2.23 (metodología de cálculo con 9 años de histórico y estimador de Huber), que sustituye al criterio inicial de usar solo el año 2024.

**Entregables:** `catalogo_ratios_masas_27sectores_huber9y.csv` (54 filas = 27 sectores × 2 segmentos, con valor Huber, número de años disponibles y último dato anual para cada uno de los 25 ratios + 13 masas de balance + 16 partidas de PyG) y `catalogo_top25roi_referencia_informativa.csv` (serie completa año a año de los segmentos "25% empresas con más ROI", de uso exclusivamente informativo — ver sección 2.23).

**Avisos de fiabilidad muestral heredados de la metodología ACCID:** Coquerías y refino de petróleo (19) y Locomotoras y material ferroviario (30.2) tienen muestras muy pequeñas de "empresas pequeñas" (3 y 12 empresas en la edición 2024 respectivamente) — sectores dominados por muy pocas grandes compañías en la realidad. Sus ratios de segmento "pequeñas" deben interpretarse con cautela si se usan para generar una empresa de tipo PYME en esos sectores.

**Nota de diseño:** durante la selección se detectó, mediante clustering estadístico, que el sector de "Carne y productos cárnicos" tiene un perfil de ratios numéricamente similar al del bloque metal/automoción/forja, pese a ser económicamente muy distinto. Se decidió mantenerlo como sector independiente por el valor de diversidad narrativa que aporta, no por diferencia estadística. Igualmente, "Fabricación de maquinaria" (28) e "Instalación de máquinas industriales" (33.2) resultaron estadísticamente similares entre sí pero se mantienen ambos por su rol estructural distinto (fabricación vs. servicio).

### 2.23. Metodología de cálculo del valor de referencia: histórico de 9 años + estimador de Huber

Confirmado como requisito. Sustituye el criterio inicial (usar solo el dato del año más reciente, 2024) por un cálculo estadísticamente fundamentado sobre un histórico más amplio.

**Fuentes utilizadas:** tres ediciones del informe ACCID "Ratios Sectoriales" cargadas por el formador: edición 2024 (cubre 2024/2023/2022), edición 2021 (cubre 2021/2020/2019) y edición 2018 (cubre 2018/2017/2016). Combinadas, forman una **serie continua de 9 años (2016-2024) sin huecos**, para los 27 sectores del catálogo. Se verificó previamente que las tres ediciones comparten metodología (178 sectores, 25 ratios, misma estructura de 4 segmentos de empresa) antes de combinarlas.

**Segmentos de empresa considerados por sector, cada año:** "grandes y medianas" (>10M€ de facturación), "25% empresas grandes y medianas con más ROI", "pequeñas" (≤10M€), "25% empresas pequeñas con más ROI" — los 4 segmentos que ya distingue el propio informe ACCID.

**Uso de cada segmento:**
- **"Grandes y medianas" y "pequeñas"**: son los segmentos que alimentan el catálogo de referencia para generar las cuentas simuladas del banco de casos.
- **Los dos segmentos "25% empresas con más ROI"**: se conservan y documentan año a año, pero **no se usan para generar las cuentas simuladas** — quedan como referencia informativa (por ejemplo, para que el formador pueda mostrar "cómo son las empresas más rentables del sector" como contraste, sin que ese dato contamine la generación de casos "típicos").

**Por qué un histórico de 9 años y no solo el último año:** se comprobó empíricamente que el año más reciente por sí solo puede no ser representativo — el análisis de la serie completa reveló que 2020 (COVID) es un año claramente atípico en varios sectores (especialmente hostelería y aeroespacial, con caídas de rentabilidad muy pronunciadas y puntuales), mientras que otros años sospechosos de antemano (2022, por la inflación/subida de tipos) resultaron ser mucho más suaves de lo esperado en la mayoría de sectores. Usar un solo año arriesga anclar el catálogo a una circunstancia coyuntural no representativa.

**Por qué el estimador de Huber y no la media o la mediana:**
- La **media aritmética simple** se deja arrastrar por años atípicos (ejemplo real detectado: en Aeroespacial, la media de ROI a 9 años es 0,002, "hundida" por el -0,11 de 2020, mientras que un valor más representativo del comportamiento habitual del sector es 0,010-0,015).
- La **mediana** es robusta a esos años atípicos, pero solo aprovecha ~64% de la información estadística disponible en la muestra (ignora la magnitud de los datos, no solo su posición).
- El **estimador de Huber** combina lo mejor de ambos: se comporta como una media para los años "normales" (usa su magnitud real) y amortigua progresivamente el peso de los años que se alejan mucho del resto, en vez de darles el mismo peso (como la media) o prácticamente ignorarlos (como la mediana). Con la constante estándar de ajuste (k = 1,345, universalmente usada en estadística robusta), alcanza aproximadamente un 95% de eficiencia estadística, frente al ~64% de la mediana.

**Cómo se calcula, en detalle:**
1. Se parte de la mediana de los 9 años como primera estimación del centro.
2. Se calcula la dispersión mediante el **MAD** (mediana de las desviaciones absolutas respecto a la mediana), reescalado dividiendo por 0,6745 para que sea comparable a una desviación típica bajo normalidad. Se usa el MAD y no la desviación típica clásica porque esta última ya estaría "contaminada" por el propio año atípico que se quiere amortiguar (razonamiento circular que el MAD evita, al basarse en la mediana).
3. Se mide la distancia de cada año respecto al centro actual, en unidades de esa dispersión (MAD reescalado).
4. A los años que se alejan menos de 1,345 unidades se les da peso completo (igual que en una media); a los que se alejan más, se les reduce el peso de forma gradual e inversamente proporcional a su distancia.
5. Se recalcula el centro con esos pesos, y se repite el proceso (pasos 3-4) hasta que el centro deja de moverse de forma apreciable (proceso iterativo).
6. El resultado final es el "valor Huber a 9 años" que se guarda en el catálogo para cada sector, segmento y variable.

**Alternativas consideradas y descartadas:** media recortada (poco margen de recorte con solo 9 datos), media ponderada por antigüedad (introduce una decisión subjetiva de pesos), media geométrica (no maneja bien los valores negativos, presentes en varios sectores en años de crisis), estimador de Hodges-Lehmann (eficiencia similar pero amortigua menos explícitamente un outlier grande y conocido como 2020).

**Qué se calcula con este método:** los 25 ratios, las 13 masas patrimoniales de balance en % (activo no corriente, activo corriente, existencias, realizable, disponible, patrimonio neto, pasivo no corriente y sus componentes, pasivo corriente y sus componentes) y las 16 partidas de la cuenta de pérdidas y ganancias en % (desde importe neto de la cifra de negocios hasta resultado del ejercicio, incluyendo margen bruto, valor añadido, BAII, BAI) — para los segmentos "grandes y medianas" y "pequeñas" de cada uno de los 27 sectores.

**Qué se guarda para cada dato:** el valor Huber a 9 años, la escala MAD usada, el número de años con dato disponible (permite detectar series incompletas), y el dato aislado del último año (2024) para poder comparar "comportamiento habitual del sector" frente a "última fotografía".

## 2.24. Especificación de la librería de arquetipos (Fase 2)

Confirmado como requisito. Da contenido operativo a la sección 2.12 (mecánica de combinación de arquetipos), definiendo los 22 arquetipos de la sección 2.7 como módulos parametrizables concretos.

**Metodología de anclaje sectorial (novedad de esta fase):** cada arquetipo con huella cuantitativa no aplica un porcentaje fijo y genérico, sino que desvía el ratio correspondiente **respecto al valor Huber de 9 años de ese ratio en el sector concreto de la empresa** (catálogo de la Fase 1, sección 2.23). Fórmula general:

```
Valor_simulado = Valor_Huber_sector[ratio] × (1 + intensidad × dirección)
```

con intensidad ∈ {0,15 leve · 0,30 moderado · 0,50 fuerte} (valores por defecto, ajustables) y dirección ∈ {+1, −1} según el arquetipo. Esto sustituye el planteamiento inicial de arquetipos con desviaciones abstractas, y hace que el mismo arquetipo produzca un caso distinto y realista según el sector elegido (p. ej. "apalancamiento" desvía la deuda de forma distinta en Refino, sector estructuralmente intensivo en capital, que en Consultoría).

**Los 22 arquetipos, con su huella de variables, ratio(s) ancla del catálogo, dirección del efecto y pista de memoria típica:**

| # | Arquetipo | Variables (huella) | Ratio(s) ancla | Dirección | Pista de memoria típica |
|---|---|---|---|---|---|
| 1 | Crecimiento con destrucción de caja | Ventas, NOF, Tesorería | rotación_existencias, cobro_días, flujo_caja_ventas | Ventas +, caja − | Fuerte crecimiento sin generación de caja proporcional |
| 2 | Beneficio sin cash flow suficiente | Resultado vs. flujo de caja | roe, flujo_caja_activo | Divergencia | El resultado no se traduce en tesorería |
| 3 | Aumento de NOF | Existencias, Clientes, Proveedores | fm_activo, rotación_existencias, cobro_días | + activo circulante | Necesidades de financiación del circulante crecientes |
| 4 | Deterioro del ciclo de caja | Plazo cobro, plazo pago | cobro_días, pago_días | + días cobro, − días pago | Alargamiento del periodo de maduración |
| 5 | Exceso de stock | Existencias, rotación | rotación_existencias, plazo_existencias | − rotación | Parte del inventario con baja rotación |
| 6 | Aumento de clientes (base) | Clientes (nº y saldo) | cobro_días | + saldo clientes | — |
| 7 | Dependencia de pocos clientes | Concentración (cualitativo) | — (solo memoria) | — | 3 clientes = 55% de ventas |
| 8 | Refinanciación | Deuda CP↔LP, calidad deuda | calidad_deuda, endeudamiento | Reestructuración | Renegociación bancaria en curso |
| 9 | Apalancamiento | Deuda, PN relativo | endeudamiento, coste_deuda | + deuda | — |
| 10 | Mejora de EBITDA | Margen operativo | margen_bruto_pct, baii_pct | + margen | — |
| 11 | Mejora de margen | Margen bruto | margen_bruto_pct | + margen | — |
| 12 | Resultado extraordinario | Resultado extraordinario ≠ 0 | resultado_extraordinario_pct | Puntual, no recurrente | Parte del resultado no es recurrente |
| 13 | Diferencias EBITDA/EBIT/beneficio/caja | Amortización, gastos financieros, impuestos | baii_pct, bai_pct, flujo_caja_ventas | Dispersión entre magnitudes | — |
| 14 | ROE elevado por apalancamiento | Deuda, ROE, ROI | endeudamiento, roe, roi | + deuda, + ROE | — |
| 15 | Riesgo de liquidez pese a beneficio | Liquidez, resultado + | liquidez, tesoreria | − liquidez | Tensión de tesorería pese a resultado positivo |
| 16 | Riesgo de refinanciación | Deuda CP con vencimiento próximo | calidad_deuda | + deuda corto plazo | Deuda relevante vence en 12 meses |
| 17 | Capex elevado | Inmovilizado, inversión | activo_no_corriente_pct, fm_activo | + activo no corriente | — |
| 18 | Adquisición | Inmovilizado puntual, fondo de comercio | activo_no_corriente_pct | + puntual, no orgánico | Adquisición explica parte del crecimiento |
| 19 | Activo mantenido para la venta | Reclasificación de un activo | — (partida específica) | — | Existe un activo que se pretende vender |
| 20 | Operaciones vinculadas | Saldos con partes vinculadas | — (solo memoria) | — | Financiación intragrupo no evidente en balance |
| 21 | Coberturas | Instrumento financiero, PN | coste_deuda | Cualitativo + PN | Cobertura de tipos de interés contratada |
| 22 | Información relevante en memoria | No modifica cifras, solo redacción | — | — | Comodín narrativo |

**Nota honesta:** los arquetipos 7, 19, 20, 21 y 22 son mayoritariamente cualitativos/de memoria — no tienen un ratio numérico claro del catálogo al que anclarse, actúan sobre la narrativa y partidas específicas del balance en vez de desviar estadísticamente un ratio sectorial. Es un comportamiento esperado, no todos los arquetipos deben tener huella cuantitativa.

**Pendiente de esta especificación (siguiente paso de la Fase 2):** construir sobre esta tabla la matriz de compatibilidad entre arquetipos (qué combinaciones son conflictivas, sección 2.12) y el cálculo formal del modelo de complejidad (solapamiento de huellas, contradicción direccional, dispersión entre estados), ambos ya definidos conceptualmente pero pendientes de aplicar sobre esta lista concreta de 22 arquetipos.

**Guía docente asociada:** cada uno de los 22 arquetipos tiene su ficha didáctica completa en el documento separado `guia_docente_arquetipos.md` — situación que encuentra el alumnado, ratios/indicadores donde se manifiesta, conclusión esperada, error habitual a evitar, y sesión recomendada (1-7). Esta guía es la base directa de: (a) la solución guiada del formador, y (b) el contenido de la ficha de solución del alumnado (sección 2.9, versión formador). Incluye también una tabla de progresión por sesiones que concreta el requisito ya definido en la sección 2.9 original.

## 2.25. Matriz de compatibilidad y modelo de complejidad (cálculo aplicado)

Confirmado como requisito, aplica formalmente la mecánica ya definida en la sección 2.12 sobre la lista concreta de 22 arquetipos de la sección 2.24.

**Base del cálculo:** cada arquetipo se representa por su conjunto de "ejes" cuantitativos afectados (variable + dirección: VENTAS, EXISTENCIAS, CLIENTES, PROVEEDORES, TESORERIA, RESULTADO, DEUDA, DEUDA_ESTRUCTURA, PN_RELATIVO, MARGEN, ROE, INMOVILIZADO, RESULTADO_EXTRA), más su conjunto de estados financieros tocados (Balance, PyG, EFE, ECPN, Memoria). El eje cualitativo "MEMORIA" se excluye del cálculo de solapamiento (varias pistas de memoria pueden coexistir sin ser redundantes entre sí) pero sí cuenta para la dispersión entre estados.

**Solapamiento** entre dos arquetipos = índice de Jaccard sobre sus ejes cuantitativos compartidos. **Contradicción** = número de ejes compartidos donde ambos arquetipos empujan en direcciones opuestas.

**Resultado sobre las 231 parejas posibles (22 arquetipos):**
- 206 parejas compatibles sin fricción relevante.
- **11 parejas redundantes** (jaccard ≥ 0,5): 2-13, 2-15, 3-4, 4-6, 8-16, 9-14, 9-21, 10-11, 13-15, 14-21, 17-18. Se recomienda no combinarlas sin refuerzo narrativo explícito, ya que aportan poca variedad nueva al caso.
- **2 parejas incompatibles** (contradicción directa de dirección): **17-19** (Capex elevado vs. Activo mantenido para la venta) y **18-19** (Adquisición vs. Activo mantenido para la venta) — ambas empujan el inmovilizado en sentidos opuestos bajo el modelo actual (que lo trata como un único eje). Estas combinaciones no se bloquean —económicamente son posibles (invertir en un área y desinvertir en otra a la vez)— pero disparan la alerta de doble confirmación de la sección 2.12.

**Entregable:** matriz completa en CSV (`matriz_compatibilidad_arquetipos.csv`, 231 filas, con jaccard, contradicción y categoría por pareja).

**Fórmula del modelo de complejidad aplicado:**

```
Complejidad(combo) = Σ_parejas [ solapamiento_jaccard + 2 × contradicción × (intensidad/0,30)² ] + 0,5 × (nº_estados_financieros_tocados − 1)
```

**Umbrales calibrados con los datos reales del cálculo:** Sencillo (<1) · Intermedio (1-2) · Avanzado (2-4) · Alerta de complejidad excesiva (>4) — sustituyen a los umbrales genéricos planteados inicialmente en la sección 2.12.

**Aviso honesto:** esta es una primera calibración basada en el diseño teórico de ejes y huellas, no en casos ya generados y validados con alumnado real. El propio diseño original (sección 2.12) ya anticipaba que el modelo necesitaría ajuste empírico tras generar y probar casos reales — este cálculo es el punto de partida, no la versión definitiva.

## 2.26. Combinaciones recomendadas de arquetipos

Confirmado como requisito. Selección curada de combinaciones de 2, 3 y 4 arquetipos, con su puntuación de complejidad real (fórmula de la sección 2.25), pensadas como punto de partida del banco de casos y como ejemplos de referencia para el formador:

| Combo | Arquetipos | Score | Estados tocados | Nivel | Sesión orientativa | Por qué interesa |
|---|---|---|---|---|---|---|
| A (2) | Exceso de stock (5) + Dependencia de clientes (7) | 0,50 | 2 | Sencillo | 3 | Combina un problema cuantitativo con uno puramente cualitativo (memoria) |
| B (2) | Crecimiento con destrucción de caja (1) + Mejora de margen (11) | 1,00 | 3 | Sencillo/Intermedio | 3 | Tensión clásica: mejora aparente en el papel, pero la caja no acompaña |
| D (3) | Mejora de EBITDA (10) + Resultado extraordinario (12) + Diferencias EBITDA/beneficio/caja (13) | 0,83 | 2 | Sencillo | 5 | Entrena la depuración de "calidad del resultado" |
| C (3) | Crecimiento con destrucción de caja (1) + Apalancamiento (9) + Riesgo de liquidez pese a beneficio (15) | 1,20 | 3 | Intermedio | 4-5 | Historia causal coherente: crece → se apalanca → tensiona caja |
| F (4) | Crecimiento con destrucción de caja (1) + Exceso de stock (5) + Apalancamiento (9) + Riesgo de refinanciación (16) | 1,75 | 4 | Intermedio/Avanzado | 6-7 | "Tormenta de liquidez" progresiva con varios frentes simultáneos |
| E (4) | Adquisición (18) + Activo para la venta (19) + Operaciones vinculadas (20) + Coberturas (21) | 4,00 | 4 | Avanzado / dispara alerta | 7 | El "paquete Empresa B" completo — sirve además como ejemplo de referencia de la alerta de doble confirmación (sección 2.12), por la pareja incompatible 18-19 |

## 3. Marco normativo

- Referencia: Plan General de Contabilidad español vigente y modelos oficiales de cuentas anuales (abreviado / normal).
- No se inventan modelos oficiales ni requisitos legales.
- Cualquier cuestión normativa sensible o susceptible de cambio se señala expresamente, indicando que debe verificarse contra la versión vigente del BOE/ICAC.
- Se distingue siempre entre: normativa / hipótesis de diseño del caso / datos simulados / cálculos derivados.

## 4. Decisiones de diseño tomadas hasta ahora

1. **Separación diseño vs. construcción.** El diseño conceptual (arquetipos, catálogo de ratios, especificación funcional) se trabaja aquí, en el chat. La construcción del software (motor de cálculo, generador de salidas, aplicación) se hace en **Claude Code**, no en el chat — por volumen de código, necesidad de ejecución/prueba iterativa y de evitar inconsistencias entre entregas parciales.

2. **Arquitectura de motor + presentación desacoplada — app web como salida elegida.** Se construye primero un motor de datos económico-financiero agnóstico de la salida final. **Decisión tomada: la presentación principal será una aplicación web** con repositorio de casos navegable (balance/PyG/memoria/ratios/dashboard), vistas separadas alumno/formador — no un Excel de múltiples hojas. El exportador a Excel queda como posible extra futuro, no como entregable principal, si en algún momento se necesita para el trabajo manual de fórmulas de algún ejercicio puntual.

3. **Fuente de ratios sectoriales reales.** Para anclar el catálogo de ratios por sector en datos reales (no solo estimaciones del modelo), se usará como fuente principal el informe **"Ratios Sectoriales" de ACCID** (coord. Oriol Amat / Pilar Lloret), publicado anualmente en PDF público y descargable, con 178 sectores CNAE y 25 ratios por sector. Se complementará si es posible con datos agregados descargables del Banco de España (Central de Balances / base RSE), teniendo en cuenta que esta última funciona principalmente como aplicación interactiva de consulta y no siempre es accesible por descarga directa. Fuentes descartadas por inaccesibilidad o no idoneidad: ICAC (no publica catálogo de ratios propio), Iberinform/Axesor (informes mayormente de pago/registro), CNMV (no es fuente pertinente para ratios de PYMES).

4. **Documento vivo de especificaciones.** Este documento (`.md`) se mantiene y actualiza a cada decisión de diseño relevante. Formato Markdown por portabilidad (convertible por cualquier LLM a Word, PDF u otro formato). Al actualizarlo, se informa con un resumen de cambios (no se repite el documento completo en el chat, salvo petición expresa).

5. **Stack técnico de infraestructura (parcial).** Base de datos y backend de la app sobre **Supabase** (el formador ya tiene experiencia previa con esta herramienta). El hosting **no está decidido**: existe la posibilidad de usar un servidor propio en Hetzner, pero esto se decidirá más adelante junto con las alternativas (PaaS gestionado tipo Vercel/Netlify/Railway, u otras). Se mantiene el uso de **GitHub** como repositorio de código y control de versiones en cualquier caso.

## 5. Plan de fases acordado

| Fase | Dónde | Contenido | Entregable al terminar |
|---|---|---|---|
| 0 | — | Decisión de herramienta y arquitectura | Este documento |
| 1 | Chat | Catálogo de ratios sectoriales reales (industrial/manufacturero, servicios industriales) | Tabla de rangos con fuente citada |
| 2 | Chat | Librería de arquetipos didácticos (situaciones financieras tipo) | Documento/JSON de arquetipos |
| 3 | Chat | Especificación funcional completa (para pasar a Claude Code) | Documento de requisitos |
| 4 | Claude Code | Motor de cálculo económico-financiero | Generador de datos coherentes, probado |
| 5 | Claude Code | Generador(es) de salida (Excel y/o app web) | Primera versión de caso navegable/exportable |
| 6 | Claude Code | Interfaz de generación ("botón") | Aplicación funcional de generación de casos |
| 7 | Ambos | Validación pedagógica con el formador | Ajustes finales, aplicación lista para uso en curso |

## 6. Cuestiones abiertas / pendientes de decidir

- Cómo se gestionará la interactividad tipo "Excel" (modificar un dato y ver cambios en cascada) dentro de la app web.
- Volumen y frecuencia de nuevos sectores/arquetipos a incorporar en el futuro (afecta al diseño del catálogo).
- **Arquitectura de la llamada a LLM para redacción/revisión de memoria.** Pendiente de decidir si esa llamada ocurre en el momento de generar cada caso (mayor coste y latencia por caso) o en un proceso aparte / por lotes.
- **Decisión de hosting.** Sin decidir aún. Opciones sobre la mesa a valorar en su momento: servidor propio en Hetzner, PaaS gestionado (Vercel/Netlify/Railway u otro), u otra alternativa. Una vez decidido, definir también el mecanismo de despliegue (manual vs. integración automatizada con GitHub Actions).
- **Modelo de despliegue de Supabase.** Decidir si se usa Supabase Cloud (gestionado, plan gratuito/de pago según uso) o Supabase autoalojado en el propio servidor de Hetzner (más control y sin depender de un tercero, pero más mantenimiento propio).
- **Gestión de usuarios/login alumno-formador.** Cómo se controla el acceso diferenciado a las dos vistas (alumno/formador) dentro de la app — a resolver con la autenticación de Supabase.

---

## 7. Log de flujo de trabajo

Registro cronológico de qué se ha hecho, en qué fase, y qué entregable ha producido. Complementa al historial de cambios (que registra decisiones de diseño); este log registra **trabajo ejecutado**.

| # | Fecha/sesión | Fase | Qué se hizo | Entregable / resultado |
|---|---|---|---|---|
| 1 | Sesión 1 | Fase 0 | Definición de arquitectura: Claude Code para construcción, chat para diseño; motor de datos desacoplado de presentación | Decisión documentada (sección 4) |
| 2 | Sesión 1 | Fase 1 (arranque) | Localización y verificación de accesibilidad de fuentes de ratios sectoriales (Banco de España, ICAC, Iberinform, ACCID, CNMV) | ACCID "Ratios Sectoriales" identificado como fuente viable; otras descartadas |
| 3 | Sesión 2 | Diseño | Definición del mecanismo de combinación de arquetipos: intensidad variable, matriz de compatibilidad, modelo de complejidad por solapamiento/contradicción/dispersión | Sección 2.12 |
| 4 | Sesión 2 | Diseño | Definición de 8 requisitos adicionales (validación sectorial, trazabilidad, variantes de examen, etc.) | Secciones 2.13-2.20 |
| 5 | Sesión 3 | Diseño | Diseño y simplificación del mecanismo de acceso del alumno a datos sectoriales de referencia | Sección 2.21 |
| 6 | Sesión 3 | Decisión de arquitectura | Confirmación de app web como salida (no Excel), stack Supabase + GitHub, hosting pendiente | Sección 4, punto 5 |
| 7 | Sesión 4 | Fase 1 | Primer intento de extracción de ratios vía `web_fetch` sobre el PDF de ACCID — limitado por truncamiento de la herramienta en documentos largos | Metodología documentada; extracción trasladada a procesamiento local del PDF |
| 8 | Sesión 4 | Fase 1 | Investigación de sectores relevantes en Euskadi (Eustat: Sector Industrial CAE 2024, Panorama de la Industria Vasca, clústeres oficiales del Gobierno Vasco) | Primera lista de 18 sectores industriales, con fuentes citadas |
| 9 | Sesión 4 | Fase 1 | Ampliación a 25 sectores (7 adicionales: siderurgia especializada, ferroviario, aeroespacial, cableado, plástico, energía eléctrica, otro material eléctrico) | Lista de 25 sectores candidatos |
| 10 | Sesión 5 | Fase 1 | Carga del PDF completo (384 páginas) por el usuario; extracción con `pdftotext`, indexado de los 178 sectores del informe, parseo estructurado de los 25 ratios por sector (formato numérico español corregido) | Script de extracción reproducible; JSON con ratios de los 25 sectores candidatos |
| 11 | Sesión 5 | Fase 1 | Análisis de similitud estadística (normalización + clustering jerárquico sobre 7 ratios representativos) para detectar redundancia entre sectores | Agrupación en 15 clusters estadísticos, con representante propuesto por grupo |
| 12 | Sesión 5 | Fase 1 | Revisión cualitativa: se detecta sobrerrepresentación de industria/metal frente a la composición real de la economía vasca (datos DIRAE: comercio/transporte/hostelería = 34,8% de establecimientos, mayor bloque) | Decisión de ampliar el catálogo más allá de industria |
| 13 | Sesión 5 | Fase 1 | Incorporación de 5 sectores de servicios (contabilidad, consultoría, logística, transporte, I+D) + 5 sectores de comercio/hostelería/construcción + 4 sectores adicionales (educación, sanidad, construcción reforzada, inmobiliario) | Catálogo ampliado a 27 sectores candidatos |
| 14 | Sesión 5 | Fase 1 | Recorte de 4 sectores industriales redundantes (cableado, cemento, papel, y consolidación de la familia eléctrica) para reequilibrar el peso del catálogo | Lista final de 27 sectores confirmada |
| 15 | Sesión 5 | Fase 1 | Extracción completa de los 25 ratios (segmentos grandes/medianas y pequeñas, 2024) para los 27 sectores finales | `catalogo_ratios_sectoriales_euskadi_27.csv` |
| 16 | Sesión 6 | Fase 1 | Comprobación de si 2023/2022 son significativamente distintos de 2024 (variación real por sector y ratio) | Confirmado: rentabilidad (ROI) varía de forma notable entre años en 17/27 sectores; liquidez/plazos más estables |
| 17 | Sesión 6 | Fase 1 | Carga de 2 ediciones adicionales del informe ACCID (2021 y 2018) por el usuario; verificación de compatibilidad metodológica; extracción y combinación en serie continua de 9 años (2016-2024) | Serie de 9 años sin huecos para los 27 sectores |
| 18 | Sesión 6 | Fase 1 | Análisis de la serie completa: identificación de 2020 (COVID) como año atípico real, no 2022 como se sospechaba inicialmente | Corrección de hipótesis inicial con datos |
| 19 | Sesión 6 | Fase 1 | Discusión y selección de estimador estadístico (media, mediana, media recortada, ponderada, geométrica, Hodges-Lehmann, Huber); elegido estimador de Huber (k=1,345, escala MAD) por mejor equilibrio precisión/robustez | Metodología documentada (sección 2.23) |
| 20 | Sesión 6 | Fase 1 (cierre ampliado) | Extracción masiva: 25 ratios + 13 masas de balance (%) + 16 partidas de PyG (%), para 4 segmentos (grandes/medianas, top25% ROI grandes/medianas, pequeñas, top25% ROI pequeñas), 3 ediciones del PDF, 27 sectores; cálculo del estimador de Huber sobre 9 años para los segmentos base | `catalogo_ratios_masas_27sectores_huber9y.csv` (54 filas × 164 columnas) y `catalogo_top25roi_referencia_informativa.csv` (26.178 filas, uso informativo) — **Fase 1 completada en su versión ampliada** |
| 21 | Sesión 6 | Fase 1 | Generación del catálogo en formato Excel (8 hojas: guía, ratios Huber/2024/n_años, balance Huber/2024, PyG Huber/2024) | `catalogo_ratios_sectoriales_euskadi.xlsx` |
| 22 | Sesión 7 | Fase 2 (arranque) | Definición de la metodología de anclaje sectorial de arquetipos (desviación de cada ratio respecto al valor Huber del sector concreto, no un porcentaje genérico); especificación completa de los 22 arquetipos de la sección 2.7 como módulos parametrizables, con huella de variables, ratio(s) ancla del catálogo, dirección del efecto y pista de memoria asociada | Sección 2.24; matriz de compatibilidad y modelo de complejidad formal quedan como siguiente paso |
| 23 | Sesión 7 | Fase 2 | Redacción de la guía docente detallada de los 22 arquetipos: situación que encuentra el alumnado, ratios/indicadores donde se manifiesta, conclusión esperada, error habitual a evitar, sesión recomendada; tabla de progresión por las 7 sesiones | `guia_docente_arquetipos.md` — base de la solución guiada del formador y de la ficha de solución del alumnado |
| 24 | Sesión 8 | Fase 2 (cierre) | Formalización de la matriz de compatibilidad (solapamiento Jaccard + contradicción direccional sobre ejes cuantitativos, MEMORIA excluida del cálculo) y del modelo de complejidad, aplicados sobre los 22 arquetipos; cálculo real de las 231 parejas posibles; propuesta y cálculo de 6 combinaciones recomendadas (2, 3 y 4 arquetipos) a distintos niveles de dificultad | Secciones 2.25 y 2.26; `matriz_compatibilidad_arquetipos.csv` (231 filas) — **Fase 2 completada** |

---

## Historial de cambios

- **v0.1** — Documento creado. Recoge el alcance funcional completo del prompt original del formador, las decisiones tomadas sobre arquitectura (Claude Code + motor/presentación desacoplados) y fuente de ratios sectoriales (ACCID), el plan de 7 fases, y las preferencias de formato/actualización del propio documento.
- **v0.2** — Completado el detalle que en v0.1 había quedado resumido o remitido al prompt original: listado íntegro de las 22 situaciones didácticas, ejemplos completos de pistas de memoria e incidencias, métricas obligatorias del dashboard, disparadores de validación, y nueva sección 2.11 con la especificación técnica y estructura de Excel originales (stack Python, checklist de 16 pasos, las 24 pestañas, y los 6 entregables), documentadas como referencia de contenido mínimo aunque el formato final de salida esté aún por decidir.
- **v0.3** — Añadida la sección 2.12: funcionalidad de combinación de varios arquetipos en un mismo caso, con sus salvaguardas de diseño (intensidad variable, matriz de compatibilidad con doble confirmación ante incompatibilidades, modelo de complejidad real basado en solapamiento/contradicción direccional/dispersión entre estados en vez de conteo simple de arquetipos, validador contable reforzado para combinaciones, y revisión de coherencia interna de las pistas de memoria). Ampliada la sección 6 con nuevas cuestiones abiertas: validador de plausibilidad sectorial, relación entre Empresa A y B, trazabilidad/reproducibilidad de cada caso, variantes de examen para evitar copia, nombres ficticios sin parecido con empresas reales, mantenimiento anual del catálogo de ratios, rúbrica de corrección del diagnóstico, control de diversidad del repositorio, y arquitectura de la llamada a LLM para la memoria (en el momento de generación o por lotes).
- **v0.4** — Confirmados como requisitos definitivos (ya no pendientes de decidir) los puntos 1 a 8 revisados en la sesión anterior: se han convertido en nuevas secciones 2.13 a 2.20 (validación de plausibilidad sectorial, relación narrativa opcional entre Empresa A y B, trazabilidad/reproducibilidad de cada caso, variantes de examen para evitar copia, nombres ficticios sin parecido con empresas reales, mantenimiento anual del catálogo de ratios, rúbrica de corrección del diagnóstico, y control de diversidad del repositorio). Solo queda pendiente de decidir el punto 9 (arquitectura de la llamada a LLM para la memoria), que permanece en la sección 6 de cuestiones abiertas.
- **v0.5** — Añadida la sección 2.21: mecanismo de acceso del alumno a los datos sectoriales de referencia, combinando secuencia hipótesis→contraste (el alumno debe emitir su juicio antes de poder consultar el dato), acceso activo no expuesto por defecto, y formato de rango por cuartiles en vez de media puntual — en ese orden de prioridad de diseño. La progresión por sesiones (referencia deshabilitada en sesiones iniciales) queda descartada por ahora como posible refinamiento futuro, no como requisito.
- **v0.6** — Simplificada la sección 2.21: eliminada la exigencia de formular una hipótesis previa (y con ella, las alternativas valoradas de desplegable, estimación numérica, comparación relativa, pistas progresivas y puesta en común grupal) por alargar excesivamente la resolución del caso. Se mantiene únicamente el acceso activo (no expuesto por defecto) y el formato de rango por cuartiles: el alumno consulta el dato sectorial solo de los ratios de los que sospeche algo, sin mecanismo de bloqueo ni feedback de acierto/error asociado.
- **v0.7** — Resuelta la decisión aplazada sobre la capa de presentación: se construirá **app web** como salida principal, no Excel. Añadido el stack de infraestructura parcialmente confirmado: **Supabase** (DB/backend) y **GitHub** (código); hosting sin decidir (Hetzner es una opción a valorar, no una decisión tomada). Actualizada la sección 6 en consecuencia.
- **v0.8** — Cambio de alcance mayor: la restricción original de "Empresa A / Empresa B" ancladas a sectores fijos (sección 2.1) queda **superada**. Añadida la sección 2.22 con el catálogo final de **27 sectores** que representan la economía vasca en su conjunto (no solo industria), construido mediante: investigación de fuentes (Eustat, clústeres oficiales, ACCID), extracción real de datos del PDF de ACCID 2024 (cargado por el usuario), análisis de similitud estadística entre sectores para eliminar redundancia, y ampliación deliberada a bloques no industriales (comercio/hostelería, construcción, administración/educación/sanidad, inmobiliario) tras detectar su infrarrepresentación frente a los datos reales de composición empresarial vasca (DIRAE). Añadida la nueva **sección 7 "Log de flujo de trabajo"**, con el registro cronológico de las 15 tareas ejecutadas hasta ahora en la Fase 1, que se dará por completada con este catálogo. Entregable generado: `catalogo_ratios_sectoriales_euskadi_27.csv`.
- **v0.9** — Ampliación mayor de la Fase 1: sustituido el criterio de "solo año 2024" por una metodología estadística sobre **histórico de 9 años (2016-2024)**, combinando tres ediciones del informe ACCID cargadas por el usuario (2024, 2021, 2018), tras comprobar que eran metodológicamente compatibles. Añadida la nueva **sección 2.23** con la explicación completa de la metodología: por qué 9 años en vez de 1, por qué se descartaron media/mediana/otras alternativas robustas, y cómo se calcula el **estimador de Huber** (k=1,345, escala MAD reescalada, proceso iterativo) elegido como valor de referencia del catálogo. Ampliado el contenido recogido por sector: además de los 25 ratios, ahora se calculan también las **13 masas patrimoniales del balance (%)** y las **16 partidas de la cuenta de pérdidas y ganancias (%)**, para los segmentos "grandes y medianas" y "pequeñas" (los usados para generar cuentas simuladas) y, por separado y solo con fines informativos (no usados en la generación), los segmentos "25% empresas con más ROI" de ambos tamaños. Entregables actualizados: `catalogo_ratios_masas_27sectores_huber9y.csv` (54 filas × 164 columnas) y `catalogo_top25roi_referencia_informativa.csv`. Actualizado el log de flujo de trabajo (sección 7) con las tareas 16-20.
- **v1.0** — Generado el catálogo también en formato Excel (`catalogo_ratios_sectoriales_euskadi.xlsx`, 8 hojas). Iniciada la **Fase 2**: añadida la sección 2.24 con la especificación completa de la librería de 22 arquetipos, incorporando la nueva metodología de **anclaje sectorial** (cada arquetipo desvía los ratios respecto al valor Huber del sector concreto de la empresa, no un porcentaje genérico y abstracto como se planteaba inicialmente en la sección 2.12). Documentados para cada arquetipo: huella de variables afectadas, ratio(s) ancla del catálogo de la Fase 1, dirección del efecto, y pista de memoria típica asociada. Pendiente como siguiente paso de la Fase 2: la matriz de compatibilidad entre arquetipos y el cálculo formal del modelo de complejidad, aplicados sobre esta lista concreta.
- **v1.1** — Creada la guía docente detallada de los 22 arquetipos (`guia_docente_arquetipos.md`): para cada uno, la situación que encuentra el alumnado, los ratios/indicadores donde se manifiesta, la conclusión a la que debe llegar, el error de interpretación habitual a evitar, y la sesión recomendada, más una tabla de progresión completa por las 7 sesiones del curso. Sirve como base directa de la solución guiada del formador y del contenido de la ficha de solución del alumnado (sección 2.9).
- **v1.2** — Cierre de la Fase 2: añadidas las secciones 2.25 (matriz de compatibilidad y modelo de complejidad calculados formalmente sobre los 22 arquetipos — 231 parejas evaluadas, 11 redundantes y 2 incompatibles detectadas, fórmula de complejidad con umbrales recalibrados a partir de los datos reales) y 2.26 (6 combinaciones recomendadas de 2, 3 y 4 arquetipos, con su puntuación de complejidad real, nivel de dificultad y sesión orientativa). Entregable: `matriz_compatibilidad_arquetipos.csv`.
- **v0.7** — Resuelta la decisión aplazada sobre la capa de presentación (punto 2 de la sección 4): se construirá **app web** como salida principal (repositorio de casos navegable, vistas alumno/formador), no Excel. Añadido el stack de infraestructura parcialmente confirmado: **Supabase** como base de datos/backend, y **GitHub** como repositorio de código en cualquier caso; el hosting queda sin decidir (se valorará Hetzner u otras alternativas más adelante). Actualizada la sección 6: eliminadas las cuestiones ya resueltas (alcance de la presentación), añadidas nuevas cuestiones abiertas: decisión de hosting (Hetzner vs. PaaS gestionado vs. otra opción) y su mecanismo de despliegue, modelo de Supabase (cloud vs. autoalojado), y gestión de usuarios/login alumno-formador.
