# kicadcomponent

Importa y elimina componentes de **LCSC / EasyEDA** en un proyecto **KiCad**,
manteniendo en sintonía las tres piezas que los componen: símbolo, footprint y
modelo 3D.

La importación la hace [`easyeda2kicad`](https://pypi.org/project/easyeda2kicad/).
Lo que añade `kicadcomponent` es lo que le falta: **saber deshacerla**, y no
tener que decirle a mano dónde está tu proyecto.

```console
$ kicadcomponent add C71459
$ kicadcomponent list
$ kicadcomponent remove C71459
```

## El problema que resuelve

Un componente se reparte en tres ficheros y **ninguno se llama como el LCSC ID**:

```
C71459  →  símbolo    MPU-9250
        →  footprint  QFN-24_L3.0-W3.0-P0.40-BL-EP
        →  modelo 3D  QFN-24_L3.0-W3.0-H0.9-P0.40-BL-EP   (.wrl + .step)
```

Borrarlo a mano implica encontrar los tres nombres y acordarse de que puede
haber otros componentes usando el mismo footprint.

No hace falta llevar una base de datos aparte, porque **la cadena entera ya está
escrita en los propios ficheros de la librería** — un índice paralelo sólo
podría desincronizarse:

| Relación | Dónde está guardada |
|---|---|
| LCSC → símbolo | `easyeda2kicad.kicad_sym` → `(property "LCSC Part" "C71459")` |
| símbolo → footprint | el mismo bloque → `(property "Footprint" "easyeda2kicad:QFN-24_…")` |
| footprint → modelo 3D | `easyeda2kicad.pretty/<fp>.kicad_mod` → `(model "…/MODELO.wrl")` |

## Instalación

Como es una herramienta de línea de comandos, mejor en un entorno aislado:

```console
$ uv tool install kicadcomponent      # o bien
$ pipx install kicadcomponent         # o bien
$ pip install kicadcomponent
```

Requiere Python ≥ 3.9 y nada más: `easyeda2kicad` se instala como dependencia y
no tiene ninguna suya. Funciona igual en Linux, macOS y Windows.

## Uso

```console
$ kicadcomponent add C71459            # símbolo + footprint + 3D
$ kicadcomponent add C71459 C22787     # varios de una vez
$ kicadcomponent add --3d C71459       # sólo el modelo 3D
$ kicadcomponent C71459                # atajo: equivale a "add"

$ kicadcomponent list                  # inventario de la librería
$ kicadcomponent where                 # qué rutas está usando

$ kicadcomponent remove C71459         # por LCSC ID
$ kicadcomponent remove MPU-9250       # o por nombre de símbolo
$ kicadcomponent remove -n C71459      # --dry-run: enseña el plan y sale
$ kicadcomponent remove -y C71459      # sin preguntar
```

Antes de borrar, enseña el plan y pide confirmación:

```console
$ kicadcomponent remove C71459
Se va a borrar de /home/carlos/proyecto/lib/easyeda2kicad:
  simbolo    MPU-9250  (C71459)
  fichero    …/easyeda2kicad.pretty/QFN-24_L3.0-W3.0-P0.40-BL-EP.kicad_mod
  fichero    …/easyeda2kicad.3dshapes/QFN-24_L3.0-W3.0-H0.9-P0.40-BL-EP.wrl
  fichero    …/easyeda2kicad.3dshapes/QFN-24_L3.0-W3.0-H0.9-P0.40-BL-EP.step
Confirmas el borrado? [y/N]
```

## Cómo encuentra tu proyecto

No hay rutas que configurar. `kicadcomponent` sube desde el directorio actual
hasta dar con un `.kicad_pro`, y a partir de ahí lee `sym-lib-table` y
`fp-lib-table`, que es donde KiCad guarda de verdad dónde vive cada librería.

Eso importa porque **la librería no tiene por qué estar dentro de la carpeta del
proyecto**. Este montaje, con dos revisiones compartiendo una librería, se
resuelve solo:

```
proyecto/
├── lib/easyeda2kicad/        ← la librería, compartida
├── v1/esp32.kicad_pro        ← ${KIPRJMOD}/../lib/easyeda2kicad/…
└── v2/esp32.kicad_pro
```

Si hace falta, se puede forzar:

```console
$ kicadcomponent --project ~/proyecto/v2 list
$ kicadcomponent --lib ~/proyecto/lib/easyeda2kicad list   # sin lib-tables
$ kicadcomponent --nickname mis-componentes list           # otro nombre
```

## Qué nunca borra

- **Footprints compartidos.** Si `R0603` lo usan dos símbolos, al quitar uno se
  borra sólo su símbolo y se avisa de quién lo sigue usando.
- **Modelos 3D compartidos**, ni los de un footprint que se conserva.
- **Footprints de otras librerías** (`Device:R` y compañía).

Además, el `.kicad_sym` se copia a `.kicad_sym.bak` antes de cada borrado. El
símbolo se recorta por su posición exacta en el fichero, así que el resto queda
byte a byte igual.

Tras borrar hay que **refrescar las librerías en KiCad** para que deje de verlo.

## Detalles de implementación

Los ficheros de KiCad se leen con un lector de s-expressions propio (sólo
biblioteca estándar) y no con expresiones regulares, porque en un mismo
`.kicad_sym` conviven dos estilos de escritura:

```lisp
; easyeda2kicad            ; KiCad al guardar desde su editor
(property                  (property "Reference" "R"
  "Reference"
  "R"
```

Y porque la ruta del `(model …)` puede venir de otra máquina
(`/home/otro/Documentos/…`), de modo que sólo es fiable el nombre del fichero.

## Licencia

MIT
