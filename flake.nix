{
  description = "Starintel synthetic data generator";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    starintel-doc.url = "github:lost-rob0t/starintel-doc/6aa8051dc7ea560943a60a25e1d600467f2778bc";
  };

  outputs = { self, nixpkgs, starintel-doc }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      pythonEnv = pkgs.python312.withPackages (ps: with ps; [
        ipython
        pytest
        # Until we need them
        #langchain
        #langchain-community
        #langchain-openai
        faker
        numpy
        pandas
        requests
        pyyaml
        python-dotenv
        pydantic
        httpx
        aiohttp
      ] ++ [
        starintel-doc.packages.${system}.default
      ]);

    in {
      packages.${system} = {
        default = pkgs.stdenv.mkDerivation {
          pname = "starintel-synthdata";
          version = "0.2.0";
          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper ];
          
          installPhase = ''
            mkdir -p $out/bin $out/lib

            # Copy Python modules
            cp *.py $out/lib/
            cp -r star_synthdata $out/lib/

            # Create wrapper script
            makeWrapper ${pythonEnv}/bin/python $out/bin/synthdata \
              --add-flags "$out/lib/main.py"
          '';
        };
      };

      checks.${system}.world = pkgs.runCommand "synthdata-world-tests" {
        nativeBuildInputs = [ pythonEnv ];
      } ''
        export PYTHONPATH=${self.packages.${system}.default}/lib
        export SYNTHDATA_CLI=${self.packages.${system}.default}/bin/synthdata
        export PYTHONDONTWRITEBYTECODE=1
        export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
        python -m pytest -q -p no:cacheprovider ${self}/tests
        $SYNTHDATA_CLI world --size 12 --output smoke
        $SYNTHDATA_CLI validate smoke
        $SYNTHDATA_CLI import-fixture smoke smoke.sqlite
        touch $out
      '';

      devShells.${system}.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          pythonEnv
          git
          jq
          curl
          ollama
        ];

        shellHook = ''
          echo "Starintel Synthetic Data Generator - Dev Environment"
          echo "=================================================="
          echo ""
          echo "Python: $(python --version)"
          echo "IPython: $(ipython --version)"
          echo ""
          echo "Available packages:"
          echo "  - langchain (+ openai, community)"
          echo "  - faker (synthetic data generation)"
          echo "  - pandas, numpy (data manipulation)"
          echo "  - httpx (ollama client)"
          echo "  - starintel-doc (document models)"
          echo "  - ipython (interactive shell)"
          echo ""
          echo "Usage:"
          echo "  python main.py person -n 5           # Generate 5 people"
          echo "  python main.py socialmediapost -n 10 # Generate 10 posts"
          echo "  python main.py message -n 20         # Generate 20 messages"
          echo ""
          echo "Run 'ipython' for interactive development"
          echo ""
        '';
      };

      apps.${system} = {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/synthdata";
        };

        ipython = {
          type = "app";
          program = "${pythonEnv}/bin/ipython";
        };
      };
    };
}
