<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { ContactShadows, Float, Environment } from '@threlte/extras';
	import { Color, Mesh } from 'three';
	import { interactivity } from '@threlte/extras';

	interactivity();

	let mesh = $state<Mesh>();
	let rotation = $state(0);

	useTask((delta) => {
		rotation += delta * 0.2;
	});

	let hovered = $state(false);
</script>

<Environment
	url="https://hebbkx1anhila5yf.public.blob.vercel-storage.com/venice_sunset_1k-76G4yKjP0X7Uu9yXz0z4yXz0z4yXz0.hdr"
	isBackground={false}
/>

<Float speed={2} rotationIntensity={0.5} floatIntensity={0.5}>
	<T.Mesh
		ref={mesh}
		rotation.y={rotation}
		onpointerenter={() => (hovered = true)}
		onpointerleave={() => (hovered = false)}
	>
		<T.IcosahedronGeometry args={[2.5, 0]} />
		<T.MeshStandardMaterial
			color={new Color(hovered ? '#60a5fa' : '#3b82f6')}
			roughness={0.1}
			metalness={0.8}
			transparent
			opacity={0.8}
		/>
	</T.Mesh>
</Float>

<ContactShadows scale={10} blur={2} far={2.5} opacity={0.5} color="#000000" />
