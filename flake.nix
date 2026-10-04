{
  description = "Starintel synthetic data generator";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    starintel-doc.url = "github:lost-rob0t/starintel-doc/ac015a5d92a1d9587e5dc7764dd9e0a150a6d0a8";
  };

  outputs = { self, nixpkgs, starintel-doc }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      pythonEnv = pkgs.python312.withPackages (ps: with ps; [
        ipython
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
          version = "0.1.0";
          src = ./.;

          nativeBuildInputs = [ pkgs.makeWrapper pkgs.python3 ];
          doCheck = true;
          doInstallCheck = true;
          checkPhase = ''
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            python3 scripts/sync-starintel-schema.py --offline
            ${pythonEnv}/bin/python -m unittest discover -s tests -v
          '';
          
          installPhase = ''
            mkdir -p $out/bin $out/lib

            # Copy Python modules
            cp -r *.py $out/lib/ 2>/dev/null || true

            # Create wrapper script
            makeWrapper ${pythonEnv}/bin/python $out/bin/synthdata \
              --add-flags "$out/lib/main.py"
          '';
          installCheckPhase = ''
            export SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
            ${pythonEnv}/bin/python tests/installed_cli.py "$out/bin/synthdata"
          '';
        };
      };

      checks.${system}.default = self.packages.${system}.default;

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
