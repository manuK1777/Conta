-- Migración: Corregir tipo_iva calculado a valor nominal 21.0
-- Fecha: 2025-04-27
-- Problema: El campo tipo_iva tenía valores calculados (20.97, 20.83, etc.)
--          en lugar del valor nominal 21.0

-- Actualizar todos los registros que tienen tipo_iva calculado incorrectamente
-- a el valor nominal 21.0 (para gastos con IVA estándar)
UPDATE gasto_deducible 
SET tipo_iva = 21.0 
WHERE tipo_iva != 0.0 
  AND tipo_iva != 21.0
  AND tipo_iva != 10.0
  AND tipo_iva != 4.0;

-- Verificación: Consultar valores distintos a los tipos estándar
-- SELECT id, proveedor, fecha, base_eur, tipo_iva, cuota_iva 
-- FROM gasto_deducible 
-- WHERE tipo_iva NOT IN (0.0, 4.0, 10.0, 21.0);
