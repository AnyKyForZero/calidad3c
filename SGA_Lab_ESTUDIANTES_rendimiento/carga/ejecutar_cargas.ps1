# Ejecuta los casos LOAD-021 a LOAD-024 con JMeter (modo consola) y mide CPU/memoria del servidor.
# Uso (desde la RAIZ del proyecto, con el entorno virtual activo y el servidor ya iniciado con waitress):
#   .\carga\ejecutar_cargas.ps1 -JMeter "C:\apache-jmeter-5.6.3\bin\jmeter.bat"            # solo 50 y 100
#   .\carga\ejecutar_cargas.ps1 -JMeter "C:\apache-jmeter-5.6.3\bin\jmeter.bat" -Hasta 300 # incluye 200 y 300 (requiere autorizacion)
param(
  [Parameter(Mandatory=$true)][string]$JMeter,
  [ValidateSet(50,100,200,300)][int]$Hasta = 100,
  [int]$Puerto = 5000
)
# caso, usuarios, rampa (s), duracion total (s)
$casos = @(
  @{id="LOAD-021"; u=50;  rampa=30;  dur=300},
  @{id="LOAD-022"; u=100; rampa=60;  dur=300},
  @{id="LOAD-023"; u=200; rampa=100; dur=300},
  @{id="LOAD-024"; u=300; rampa=150; dur=300}
)
if ($Hasta -ge 200) {
  $ok = Read-Host "200 y 300 usuarios requieren autorizacion del docente e infraestructura suficiente. Escriba SI para continuar"
  if ($ok -ne "SI") { Write-Host "Cancelado."; exit }
}
New-Item -ItemType Directory -Force -Path carga\resultados | Out-Null
foreach ($c in $casos) {
  if ($c.u -gt $Hasta) { continue }
  Write-Host "`n=== $($c.id): $($c.u) usuarios virtuales ===" -ForegroundColor Cyan
  Remove-Item -Recurse -Force "carga\resultados\$($c.id)_reporte" -ErrorAction SilentlyContinue
  Remove-Item -Force "carga\resultados\$($c.id).jtl" -ErrorAction SilentlyContinue
  $mon = Start-Process python -ArgumentList "carga\monitor_recursos.py --puerto $Puerto --salida carga\resultados\$($c.id)_recursos.csv --duracion $($c.dur + 10)" -PassThru -WindowStyle Hidden
  & $JMeter -n -t carga\plan_SGA.jmx "-Jusuarios=$($c.u)" "-Jrampa=$($c.rampa)" "-Jduracion=$($c.dur)" "-Jpuerto=$Puerto" "-Jjmeter.save.saveservice.subresults=false" -l "carga\resultados\$($c.id).jtl" -e -o "carga\resultados\$($c.id)_reporte"
  Wait-Process -Id $mon.Id -ErrorAction SilentlyContinue
  python carga\resumir_resultados.py --jtl "carga\resultados\$($c.id).jtl" --caso $c.id --usuarios $c.u --recursos "carga\resultados\$($c.id)_recursos.csv"
  Write-Host "Descanso de 60 s antes del siguiente nivel..."; Start-Sleep -Seconds 60
}
Write-Host "`nListo. Resumen acumulado: carga\resultados\resumen_rendimiento.csv"
