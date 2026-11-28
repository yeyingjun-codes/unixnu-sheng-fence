// BootShim PSCI diagnostic screen. Each hex digit is shown as a 4x7
// binary matrix: one lit column per set bit in the nibble (MSB left).
// Row 1 white = PSCI_VERSION low 32 bits; row 2 orange = FEATURES reset.
// A left white square proves framebuffer writes; two rows prove SMC results.

_Head:
  adr   x1, _Payload
  b     _Start

  .quad FD_BASE
  .quad FD_SIZE + (_Payload - _Head)
  .quad 0
  .quad 0
  .quad 0
  .quad 0
  .ascii "ARM\x64"
  .long 0

_Start:
  /* Fill framebuffer dark blue: 3048*2032 pixels. */
  movz  x0, #0
  movk  x0, #0xb800, lsl #16
  movz  x1, #0xd260
  movk  x1, #0x005e, lsl #16
  movz  w2, #0x40
1:
  str   w2, [x0], #4
  subs  x1, x1, #1
  b.ne  1b
  dsb   sy

  /* White square at top-left: proof entry and framebuffer writes work. */
  mov   x4, #100
  mov   x5, #100
  mov   w3, #0xff
  movk  w3, #0xffff, lsl #16
  bl    box

  /* PSCI_VERSION. */
  movz  x0, #0
  movk  x0, #0x8400, lsl #16
  mov   x1, xzr
  mov   x2, xzr
  mov   x3, xzr
  smc   #0
  mov   x10, x0
  mov   x4, #240
  mov   x5, #100
  mov   w3, #0xff
  movk  w3, #0xffff, lsl #16
  bl    value32

  /* PSCI_FEATURES(SYSTEM_RESET). */
  movz  x0, #0x000a
  movk  x0, #0x8400, lsl #16
  movz  x1, #0x0009
  movk  x1, #0x8400, lsl #16
  mov   x2, xzr
  mov   x3, xzr
  smc   #0
  mov   x10, x0
  mov   x4, #240
  mov   x5, #420
  movz  w3, #0x8000
  movk  w3, #0x00ff, lsl #16
  bl    value32

  dsb   sy
_Dead:
  wfe
  b     _Dead

/* Draw 8 hex nibbles from w10, MSB first, x=x4,y=x5,color=w3.
   Each nibble is 4 lit columns, height 60 pixels, 40 pixels pitch. */
value32:
  stp   x29, x30, [sp, #-32]!
  mov   x29, sp
  stp   x19, x20, [sp, #16]
  mov   x19, #28
1:
  lsr   w20, w10, w19
  and   w20, w20, #15
  mov   x6, #0
2:
  mov   w12, #1
  lsl   w12, w12, w6
  and   w12, w20, w12
  cbz   w12, 3f
  mov   x7, x4
  mov   x8, x5
  mov   w9, w3
  mov   x13, #10
  mov   x14, #60
  bl    rect
3:
  add   x4, x4, #10
  add   x6, x6, #1
  cmp   x6, #4
  b.lt  2b
  add   x4, x4, #40
  subs  x19, x19, #4
  b.pl  1b
  ldp   x19, x20, [sp, #16]
  ldp   x29, x30, [sp], #32
  ret

/* Solid rectangle: x=x7,y=y8,w=x13,h=x14,color=w9. */
rect:
  sub   sp, sp, #48
  stp   x19, x20, [sp]
  stp   x21, x22, [sp, #16]
  str   x30, [sp, #32]
  mov   x20, x4
  mov   x21, x5
  mov   x15, #0
1:
  mov   x16, #0
2:
  add   x17, x7, x16
  add   x18, x8, x15
  mov   x22, #3048
  madd  x18, x18, x22, x17
  movz  x22, #0
  movk  x22, #0xb800, lsl #16
  str   w9, [x22, x18, lsl #2]
  add   x16, x16, #1
  cmp   x16, x13
  b.lt  2b
  add   x15, x15, #1
  cmp   x15, x14
  b.lt  1b
  mov   x4, x20
  mov   x5, x21
  ldp   x19, x20, [sp]
  ldp   x21, x22, [sp, #16]
  ldr   x30, [sp, #32]
  add   sp, sp, #48
  ret

/* White 100x100 entry box at x=x4,y=x5,color=w3. */
box:
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  mov   x7, x4
  mov   x8, x5
  mov   w9, w3
  mov   x13, #100
  mov   x14, #100
  bl    rect
  ldp   x29, x30, [sp], #16
  ret

.text
.ltorg
.align 4
_Payload:
