fsrs_optimizer_rust/:
	cd fsrs-optimizer-burn && \
	maturin build -r
	
	pip install fsrs-optimizer-burn/target/wheels/*.whl --target .
