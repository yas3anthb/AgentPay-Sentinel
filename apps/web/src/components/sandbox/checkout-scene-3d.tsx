"use client";

import { Line, RoundedBox, Text } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

import { CHECKOUT_STEPS, type CheckoutStep } from "@/lib/checkout-sandbox";

const SPACING = 2.0;
// A distinct, cooler blue family from the product's own indigo accent — the
// palette itself signals "this panel is a different thing," reinforcing the
// simulated/illustrative label rather than contradicting it.
const RAZORPAY_BLUE = "#2563EB";
const IDLE = "#CBD5E1";
const GROUND = "#EEF4FF";
const DECLINE = "#C2334A";

function stepIndex(step: CheckoutStep): number {
  if (step === "idle" || step === "not_reached") return -1;
  if (step === "declined") return 3;
  return CHECKOUT_STEPS.findIndex((s) => s.id === step);
}

function CheckoutNode({
  index,
  activeIndex,
  declined,
  reducedMotion,
}: {
  index: number;
  activeIndex: number;
  declined: boolean;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const passed = activeIndex > index || (activeIndex === index && index === 3 && !declined);
  const current = activeIndex === index;
  const isDeclineNode = declined && index === 3;
  const color = isDeclineNode ? DECLINE : current || passed ? RAZORPAY_BLUE : IDLE;
  const active = current || passed;

  useFrame((_, delta) => {
    if (reducedMotion || !group.current) return;
    if (current && !declined) group.current.rotation.y += delta * 0.8;
  });

  return (
    <group position={[index * SPACING, 0, 0]}>
      <group ref={group}>
        <RoundedBox args={[0.72, 0.72, 0.72]} radius={0.12} smoothness={4}>
          <meshStandardMaterial color={active ? color : "#FFFFFF"} roughness={0.5} />
        </RoundedBox>
        <RoundedBox args={[0.74, 0.74, 0.74]} radius={0.13} smoothness={4}>
          <meshBasicMaterial color={color} wireframe transparent opacity={0.3} />
        </RoundedBox>
      </group>
      {current && !reducedMotion ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.58, 0]}>
          <ringGeometry args={[0.48, 0.54, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} />
        </mesh>
      ) : null}
      <Text position={[0, -0.78, 0]} fontSize={0.135} color={active ? "#1A2233" : "#94A3B8"} anchorX="center" anchorY="top">
        {CHECKOUT_STEPS[index].label}
      </Text>
    </group>
  );
}

function Rail({ activeIndex, declined }: { activeIndex: number; declined: boolean }) {
  const segments = [];
  for (let i = 0; i < CHECKOUT_STEPS.length - 1; i += 1) {
    const filled = activeIndex > i && !(declined && i >= 2);
    segments.push(
      <Line
        key={i}
        points={[
          [i * SPACING + 0.46, 0, 0],
          [(i + 1) * SPACING - 0.46, 0, 0],
        ]}
        color={filled ? RAZORPAY_BLUE : "#D2D7E0"}
        lineWidth={filled ? 2.5 : 1.5}
        dashed={!filled}
        dashSize={0.07}
        gapSize={0.07}
      />,
    );
  }
  return <>{segments}</>;
}

export function CheckoutScene3D({
  step,
  reducedMotion,
}: {
  step: CheckoutStep;
  reducedMotion: boolean;
}) {
  const activeIndex = stepIndex(step);
  const declined = step === "declined";
  const centre = ((CHECKOUT_STEPS.length - 1) * SPACING) / 2;

  return (
    <Canvas camera={{ position: [centre, 2.1, 6.5], fov: 34 }} gl={{ antialias: true }}>
      <color attach="background" args={[GROUND]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[3, 5, 4]} intensity={0.55} />
      <group position={[-centre, 0, 0]}>
        {CHECKOUT_STEPS.map((s, i) => (
          <CheckoutNode
            key={s.id}
            index={i}
            activeIndex={activeIndex}
            declined={declined}
            reducedMotion={reducedMotion}
          />
        ))}
        <Rail activeIndex={activeIndex} declined={declined} />
        <gridHelper args={[16, 16, "#D6E3FA", "#E8EFFC"]} position={[centre, -1.15, 0]} />
      </group>
    </Canvas>
  );
}
